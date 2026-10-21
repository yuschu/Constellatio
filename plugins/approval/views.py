"""approval 插件视图：发起 / 我的审批 / 待我审批 / 详情操作。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Approval
from .services import approve, reject, submit

User = get_user_model()


def _can_act(user, approval):
    """审批操作人校验：审批人本人 或 具备 approval_approve 权限。"""
    return user == approval.approver or user.has_perm('approval_approve')


@login_required
def approval_list(request):
    """我发起的审批。"""
    approvals = Approval.objects.filter(applicant=request.user)
    return render(request, 'approval/approval_list.html', {'approvals': approvals})


@login_required
def approval_pending(request):
    """待我审批。"""
    approvals = Approval.objects.filter(
        approver=request.user, status=Approval.Status.PENDING)
    return render(request, 'approval/approval_pending.html', {'approvals': approvals})


@login_required
def approval_create(request):
    """发起审批（提交即进入待审批）。"""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        approver_id = request.POST.get('approver')
        if title and approver_id:
            approval = Approval.objects.create(
                approval_type=request.POST.get('approval_type') or Approval.Type.LEAVE,
                title=title,
                content=request.POST.get('content', ''),
                amount=request.POST.get('amount') or None,
                applicant=request.user,
                approver_id=approver_id)
            submit(approval, request.user, '发起审批')
            return redirect('approval:approval_list')
    users = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by('username')
    return render(request, 'approval/approval_form.html', {'users': users})


@login_required
def approval_detail(request, approval_id):
    """审批详情 + 通过/驳回操作。"""
    approval = get_object_or_404(Approval, pk=approval_id)
    involved = approval.applicant == request.user or approval.approver == request.user
    if not involved and not request.user.has_perm('approval_view'):
        return redirect('index')

    if request.method == 'POST':
        if not _can_act(request.user, approval):
            return redirect('index')
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        try:
            if action == 'approve':
                approve(approval, request.user, comment)
            elif action == 'reject':
                reject(approval, request.user, comment)
        except ValueError:
            pass
        return redirect('approval:approval_detail', approval_id=approval.id)

    return render(request, 'approval/approval_detail.html', {
        'approval': approval,
        'records': approval.records.all(),
        'can_act': _can_act(request.user, approval),
    })
