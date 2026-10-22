"""审批状态机流转逻辑（services 层，保证可单测）。

v1.2 新增会签（counter signature）：部门删除 / 用户禁用走会签单，
全部会签人（具备对应权限码的管理员）通过后才 approved 并回调执行方。
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from plugin_host.signals import approval_finished, counter_signature_approved

from .models import Approval, ApprovalRecord

User = get_user_model()


def _record(approval, operator, action, comment):
    return ApprovalRecord.objects.create(
        approval=approval, operator=operator, action=action, comment=comment)


def _cc_approver_superior(approval):
    """抄送审批人的上级（v1.5.5）：审批人收到申请时、审批完成时各抄送一次（幂等）。"""
    if not approval.approver_id:
        return None
    superior = approval.approver.leader
    if superior and superior.pk != approval.approver_id:
        approval.cc_users.add(superior)
        return superior
    return None


def submit(approval, operator, comment=''):
    """草稿/待审批 → 待审批；同时抄送审批人的上级。"""
    if approval.status not in (Approval.Status.DRAFT, Approval.Status.PENDING):
        raise ValueError('只有草稿/待审批状态可提交')
    approval.status = Approval.Status.PENDING
    approval.save(update_fields=['status', 'updated_at'])
    _record(approval, operator, 'submit', comment)
    _cc_approver_superior(approval)


def approve(approval, operator, comment=''):
    """待审批 → 已通过（普通审批）；结果同步申请人，并抄送审批人上级。"""
    if approval.status != Approval.Status.PENDING:
        raise ValueError('只有待审批状态可通过')
    approval.status = Approval.Status.APPROVED
    approval.save(update_fields=['status', 'updated_at'])
    _record(approval, operator, 'approve', comment)
    _cc_approver_superior(approval)
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='approved')


def reject(approval, operator, comment=''):
    """待审批 → 已驳回（普通审批 / 会签任一驳回）；结果同步申请人，并抄送审批人上级。"""
    if approval.status != Approval.Status.PENDING:
        raise ValueError('只有待审批状态可驳回')
    approval.status = Approval.Status.REJECTED
    approval.save(update_fields=['status', 'updated_at'])
    _record(approval, operator, 'reject', comment)
    _cc_approver_superior(approval)
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='rejected')


def start_counter_signature(approval, signers, operator, comment=''):
    """为已创建的审批单建立会签集合并进入待审批。

    signers：具备对应审批权限码的管理员（含超管）。signers 为空则抛错（无法通过）。
    """
    if not signers:
        raise ValueError('无具备审批权限的管理员，无法发起会签')
    approval.status = Approval.Status.PENDING
    approval.save(update_fields=['status', 'updated_at'])
    for signer in signers:
        approval.signers.create(signer=signer)
    _record(approval, operator, 'submit', comment or '发起会签')


def _mark_signed(approval, operator, comment):
    signer_row = approval.signers.filter(signer=operator).first()
    if signer_row is None:
        raise ValueError('您不是本单的会签人')
    if signer_row.signed:
        raise ValueError('您已签过')
    signer_row.signed = True
    signer_row.signed_at = timezone.now()
    signer_row.comment = comment
    signer_row.save(update_fields=['signed', 'signed_at', 'comment'])
    return signer_row


def sign_approve(approval, operator, comment=''):
    """会签通过：仅会签人本人可签；全部签完 → approved + counter_signature_approved 回调。"""
    if approval.status != Approval.Status.PENDING:
        raise ValueError('只有待审批状态可会签')
    _mark_signed(approval, operator, comment)
    _record(approval, operator, 'sign_approve', comment)

    if not approval.signers.filter(signed=False).exists():
        approval.status = Approval.Status.APPROVED
        approval.save(update_fields=['status', 'updated_at'])
        approval_finished.send(sender=approval.__class__, approval_id=approval.id,
                               result='approved')
        # 回调执行方（user 插件订阅）：物理删除 / 禁用
        counter_signature_approved.send(
            sender=approval.__class__, approval_id=approval.id,
            biz_type=approval.approval_type, biz_id=approval.biz_id,
            operator_id=operator.pk)


def sign_reject(approval, operator, comment=''):
    """会签驳回：任一会签人驳回即 rejected（不再继续）。"""
    if approval.status != Approval.Status.PENDING:
        raise ValueError('只有待审批状态可会签')
    _mark_signed(approval, operator, comment)
    _record(approval, operator, 'sign_reject', comment)
    approval.status = Approval.Status.REJECTED
    approval.save(update_fields=['status', 'updated_at'])
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='rejected')
