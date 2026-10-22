"""approval 插件视图：发起 / 我的审批 / 待我审批 / 抄送我的 / 详情操作。"""

from django.apps import apps as dj_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from plugin_host.permissions import require_perm

from . import forms
from .models import Approval
from .services import approve, reject, sign_approve, sign_reject, submit

User = get_user_model()


def _can_act(user, approval):
    """审批操作人校验：
    - 会签单：必须是会签人本人且未签
    - 普通单：审批人本人 或 具备 approval_approve 权限
    """
    if approval.is_counter_signature():
        row = approval.signers.filter(signer=user).first()
        return row is not None and not row.signed
    if approval.approver_id is None:
        return False
    return user == approval.approver or user.has_perm('approval_approve')


def _departments():
    """跨插件零 import：动态取 user.Department；插件停用时降级为空。"""
    try:
        Department = dj_apps.get_model('user', 'Department')
    except LookupError:
        return []
    return Department.objects.filter(is_active=True).order_by('name')


def _overtime_choices(user):
    """调休依据：本人近一年未被驳回的加班审批。"""
    rows = Approval.objects.filter(
        applicant=user, approval_type=Approval.Type.OVERTIME,
    ).exclude(status=Approval.Status.REJECTED).order_by('-created_at')[:50]
    choices = []
    for row in rows:
        start = row.form_data.get('start_time', '')
        end = row.form_data.get('end_time', '')
        label = f'#{row.pk} {start} ~ {end}' if start or end else f'#{row.pk} {row.title}'
        choices.append((str(row.pk), label))
    return choices


def _resolve_approver(applicant, approver_id):
    """审批人：显式选择 → 直属上级 → 兜底启用中的超管。"""
    if approver_id:
        chosen = User.objects.filter(pk=approver_id, is_active=True).first()
        if chosen is not None:
            return chosen
    if applicant.leader_id and applicant.leader and applicant.leader.is_active:
        return applicant.leader
    return User.objects.filter(is_superuser=True, is_active=True).order_by('pk').first()


def _summary(approval_type, cleaned, basis_label=''):
    """把动态字段拼成 human-readable 内容（同时保留原始 form_data）。"""
    lines = []
    for name, label in forms.type_fields(approval_type):
        value = cleaned.get(name)
        if value in (None, ''):
            continue
        if name == 'basis' and basis_label:
            value = basis_label
        lines.append(f'{label}：{value}')
    return '\n'.join(lines)


@require_perm('approval_view')
def approval_list(request):
    """我发起的审批。"""
    approvals = Approval.objects.filter(applicant=request.user)
    return render(request, 'approval/approval_list.html', {'approvals': approvals})


@require_perm('approval_view')
def approval_pending(request):
    """待我审批：普通单（approver=我） + 会签单（我是 signer 且未签）。"""
    approvals = Approval.objects.filter(
        approver=request.user, status=Approval.Status.PENDING)
    counter = Approval.objects.filter(
        status=Approval.Status.PENDING,
        signers__signer=request.user, signers__signed=False)
    merged = list(approvals) + [a for a in counter if a not in approvals]
    return render(request, 'approval/approval_pending.html', {'approvals': merged})


@require_perm('approval_view')
def approval_cc(request):
    """抄送我的：审批人上级自动抄送的申请（发起时 + 审批完成时）。"""
    approvals = request.user.cc_approvals.select_related(
        'applicant', 'approver').order_by('-created_at')
    return render(request, 'approval/approval_cc.html', {'approvals': approvals})


@require_perm('approval_view')
def approval_create(request):
    """发起审批：按类型渲染动态表单（v1.5.5）。"""
    type_key = request.GET.get('type') or request.POST.get('approval_type') \
        or Approval.Type.LEAVE
    if type_key not in forms.FORM_CLASSES:
        type_key = Approval.Type.LEAVE

    departments = _departments()
    approvers = User.objects.filter(is_active=True).exclude(
        pk=request.user.pk).order_by('last_name', 'username')
    overtime_choices = _overtime_choices(request.user)
    form = forms.form_for_type(
        type_key, request.POST or None, applicant=request.user,
        departments=departments, approvers=approvers,
        overtime_choices=overtime_choices)

    if request.method == 'POST' and form.is_valid():
        Department = None
        if departments:
            Department = departments.model
        department = None
        if Department is not None:
            department = Department.objects.filter(
                pk=form.cleaned_data['department']).first()
        approver = _resolve_approver(request.user, form.cleaned_data.get('approver'))
        if department is None:
            form.add_error('department', '请选择有效部门')
        elif approver is None:
            form.add_error('approver', '未指定审批人，且当前账号没有直属上级')
        else:
            form_data = {}
            for name, _label in forms.type_fields(type_key):
                value = form.cleaned_data.get(name)
                if value not in (None, ''):
                    form_data[name] = str(value)
            basis_id = form_data.get('basis')
            basis_label = ''
            if basis_id:
                basis_label = dict(overtime_choices).get(str(basis_id), '')
                if basis_label:
                    form_data['basis_label'] = basis_label
            approval = Approval.objects.create(
                approval_type=type_key,
                title=f'{Approval.Type(type_key).label}｜{request.user.last_name or request.user.username}',
                content=_summary(type_key, form.cleaned_data, basis_label),
                applicant=request.user,
                approver=approver,
                department_id=department.pk,
                department_name=department.name,
                form_data=form_data)
            submit(approval, request.user, '发起审批')
            return redirect('approval:approval_list')

    return render(request, 'approval/approval_form.html', {
        'form': form,
        'type_key': type_key,
        'types': [{'key': key, 'label': Approval.Type(key).label}
                  for key in forms.FORM_TYPES],
        'users': approvers,
    })


@login_required
def approval_detail(request, approval_id):
    """审批详情 + 通过/驳回（普通） + 会签通过/驳回（会签单）。"""
    approval = get_object_or_404(Approval, pk=approval_id)
    involved = approval.applicant_id == request.user.pk or approval.approver_id == request.user.pk
    if not involved and not request.user.has_perm('approval_view'):
        return redirect('index')

    if request.method == 'POST':
        if not _can_act(request.user, approval):
            return redirect('index')
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        try:
            if approval.is_counter_signature():
                if action == 'sign_approve':
                    sign_approve(approval, request.user, comment)
                elif action == 'sign_reject':
                    sign_reject(approval, request.user, comment)
            else:
                if action == 'approve':
                    approve(approval, request.user, comment)
                elif action == 'reject':
                    reject(approval, request.user, comment)
        except ValueError:
            pass
        return redirect('approval:approval_detail', approval_id=approval.id)

    form_rows = []
    for name, label in forms.type_fields(approval.approval_type):
        value = approval.form_data.get(name, '')
        if name == 'basis':
            value = approval.form_data.get('basis_label', value)
        form_rows.append((label, value or '—'))

    return render(request, 'approval/approval_detail.html', {
        'approval': approval,
        'records': approval.records.all(),
        'signers': approval.signers.all(),
        'can_act': _can_act(request.user, approval),
        'is_counter': approval.is_counter_signature(),
        'form_rows': form_rows,
        'cc_users': approval.cc_users.all(),
    })
