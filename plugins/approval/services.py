"""审批状态机流转逻辑（services 层，保证可单测）。

v1.2 新增会签（counter signature）：部门删除 / 用户禁用走会签单，
全部会签人（具备对应权限码的管理员）通过后才 approved 并回调执行方。

v1.7.x 并发加固（P0-6）：
- 每个流转函数在 ``transaction.atomic()`` 内用 ``select_for_update()`` 重新读取
  审批单，状态判断与写操作基于同一行锁内的一致快照，避免并发重复流转；
- 普通审批额外校验操作人必须是单据审批人（超管兜底），防止跨单越权；
- 会签标记改为条件更新（``signed=False`` 才更新），天然幂等；
- 业务信号在事务块之外同步发送：保持既有行为（TestCase 内不依赖 commit），
  订阅方（留痕 / 站内信）的失败由各自 handler 隔离，不影响状态机结果。
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from plugin_host.signals import (
    approval_finished,
    approval_submitted,
    counter_signature_approved,
)

from .models import Approval, ApprovalRecord

User = get_user_model()


def _record(approval, operator, action, comment):
    return ApprovalRecord.objects.create(
        approval=approval, operator=operator, action=action, comment=comment)


def _locked(approval):
    """在事务内取审批单行锁实例：状态判断与写操作必须基于该实例。"""
    return Approval.objects.select_for_update().get(pk=approval.pk)


def _cc_applicant_leader(approval):
    """抄送申请人的直系领导（v1.5.18）：发起与审批完成时各抄送一次（幂等）。

    若直系领导就是申请人本人或审批人，则跳过（无需重复通知）。
    """
    leader = approval.applicant.leader if approval.applicant.leader_id else None
    if leader and leader.pk not in {approval.applicant_id, approval.approver_id}:
        approval.cc_users.add(leader)
        return leader
    return None


def submit(approval, operator, comment='', action='submit'):
    """草稿/待审批 → 待审批；同时抄送申请人的直系领导。

    action 默认为 submit；重新申请时传 resubmit 以区分留痕（v1.5.16）。
    """
    with transaction.atomic():
        locked = _locked(approval)
        if locked.status not in (Approval.Status.DRAFT, Approval.Status.PENDING):
            raise ValueError('只有草稿/待审批状态可提交')
        locked.status = Approval.Status.PENDING
        locked.save(update_fields=['status', 'updated_at'])
        _record(locked, operator, action, comment)
        _cc_applicant_leader(locked)
    approval_submitted.send(
        sender=Approval, approval_id=locked.pk, operator_id=operator.pk)


def approve(approval, operator, comment=''):
    """待审批 → 已通过（普通审批）；结果同步申请人，并抄送审批人上级。

    行锁内先校验操作人（审批人本人或超管），再校验状态，最后落库。
    """
    with transaction.atomic():
        locked = _locked(approval)
        if locked.approver_id != operator.pk and not operator.is_superuser:
            raise PermissionError('您不是该单据的审批人')
        if locked.status != Approval.Status.PENDING:
            raise ValueError('只有待审批状态可通过')
        locked.status = Approval.Status.APPROVED
        locked.save(update_fields=['status', 'updated_at'])
        _record(locked, operator, 'approve', comment)
        _cc_applicant_leader(locked)
        # v1.5.15：用章通过后执行电子盖章（当前为占位文本，待电子章插件接入）
        if locked.approval_type == Approval.Type.SEAL:
            from .eseal import apply_e_seal
            _record(locked, operator, 'e_seal', apply_e_seal(locked))
    approval_finished.send(sender=Approval, approval_id=locked.pk, result='approved')


def reject(approval, operator, comment=''):
    """待审批 → 已驳回（普通审批 / 会签任一驳回）；结果同步申请人，并抄送审批人上级。

    行锁内先校验操作人（审批人本人或超管），再校验状态，最后落库。
    """
    with transaction.atomic():
        locked = _locked(approval)
        if locked.approver_id != operator.pk and not operator.is_superuser:
            raise PermissionError('您不是该单据的审批人')
        if locked.status != Approval.Status.PENDING:
            raise ValueError('只有待审批状态可驳回')
        locked.status = Approval.Status.REJECTED
        locked.save(update_fields=['status', 'updated_at'])
        _record(locked, operator, 'reject', comment)
        _cc_applicant_leader(locked)
    approval_finished.send(sender=Approval, approval_id=locked.pk, result='rejected')


def start_counter_signature(approval, signers, operator, comment=''):
    """为已创建的审批单建立会签集合并进入待审批。

    signers：具备对应审批权限码的管理员（含超管）。signers 为空则抛错（无法通过）。
    """
    if not signers:
        raise ValueError('无具备审批权限的管理员，无法发起会签')
    with transaction.atomic():
        locked = _locked(approval)
        locked.status = Approval.Status.PENDING
        locked.save(update_fields=['status', 'updated_at'])
        for signer in signers:
            locked.signers.create(signer=signer)
        _record(locked, operator, 'submit', comment or '发起会签')
    approval_submitted.send(
        sender=Approval, approval_id=locked.pk, operator_id=operator.pk)


def _mark_signed(approval, operator, comment):
    """条件更新标记本人已签；影响行数为 0 说明已被并发签过。

    调用方必须已持有该审批单的行锁（外层事务），本函数只做单行条件更新。
    """
    signer_row = approval.signers.filter(signer=operator).first()
    if signer_row is None:
        raise ValueError('您不是本单的会签人')
    signed_at = timezone.now()
    updated = approval.signers.filter(pk=signer_row.pk, signed=False).update(
        signed=True, signed_at=signed_at, comment=comment)
    if updated != 1:
        raise ValueError('您已签过')
    return signer_row


def sign_approve(approval, operator, comment=''):
    """会签通过：仅会签人本人可签；全部签完 → approved + counter_signature_approved 回调。"""
    finished = False
    with transaction.atomic():
        locked = _locked(approval)
        if locked.status != Approval.Status.PENDING:
            raise ValueError('只有待审批状态可会签')
        _mark_signed(locked, operator, comment)
        _record(locked, operator, 'sign_approve', comment)
        # 终态判定同样在行锁内：避免最后两人并发时重复触发回调
        if not locked.signers.filter(signed=False).exists():
            locked.status = Approval.Status.APPROVED
            locked.save(update_fields=['status', 'updated_at'])
            finished = True
    if finished:
        approval_finished.send(sender=Approval, approval_id=locked.pk,
                               result='approved')
        # 回调执行方（user 插件订阅）：物理删除 / 禁用
        counter_signature_approved.send(
            sender=Approval, approval_id=locked.pk,
            biz_type=locked.approval_type, biz_id=locked.biz_id,
            operator_id=operator.pk)


def sign_reject(approval, operator, comment=''):
    """会签驳回：任一会签人驳回即 rejected（不再继续）。"""
    with transaction.atomic():
        locked = _locked(approval)
        if locked.status != Approval.Status.PENDING:
            raise ValueError('只有待审批状态可会签')
        _mark_signed(locked, operator, comment)
        _record(locked, operator, 'sign_reject', comment)
        locked.status = Approval.Status.REJECTED
        locked.save(update_fields=['status', 'updated_at'])
    approval_finished.send(sender=Approval, approval_id=locked.pk, result='rejected')
