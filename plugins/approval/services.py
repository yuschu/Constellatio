"""审批状态机流转逻辑（services 层，保证可单测）。"""

from plugin_host.signals import approval_finished

from .models import Approval, ApprovalRecord


def _record(approval, operator, action, comment):
    return ApprovalRecord.objects.create(
        approval=approval, operator=operator, action=action, comment=comment)


def submit(approval, operator, comment=''):
    """草稿/待审批 → 待审批。"""
    if approval.status not in (Approval.Status.DRAFT, Approval.Status.PENDING):
        raise ValueError('只有草稿/待审批状态可提交')
    approval.status = Approval.Status.PENDING
    approval.save(update_fields=['status', 'updated_at'])
    _record(approval, operator, 'submit', comment)


def approve(approval, operator, comment=''):
    """待审批 → 已通过。"""
    if approval.status != Approval.Status.PENDING:
        raise ValueError('只有待审批状态可通过')
    approval.status = Approval.Status.APPROVED
    approval.save(update_fields=['status', 'updated_at'])
    _record(approval, operator, 'approve', comment)
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='approved')


def reject(approval, operator, comment=''):
    """待审批 → 已驳回。"""
    if approval.status != Approval.Status.PENDING:
        raise ValueError('只有待审批状态可驳回')
    approval.status = Approval.Status.REJECTED
    approval.save(update_fields=['status', 'updated_at'])
    _record(approval, operator, 'reject', comment)
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='rejected')
