"""approval 插件视图：发起 / 我的审批 / 待我审批 / 抄送我的 / 详情操作。"""

from datetime import timedelta

from django.apps import apps as dj_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from plugin_host.permissions import require_perm

from . import forms
from .models import Approval, ApprovalRecord
from .routing import candidate_approvers as resolve_candidates
from .services import approve, reject, sign_approve, sign_reject, submit

User = get_user_model()

# v1.7.1（P1-20）：列表统一分页 25 条/页
LIST_PAGE_SIZE = 25


def _may_view(user, approval):
    """对象级可见性（v1.7.1 / P0-9）：申请人 / 审批人 / 会签人 / 抄送人 / 超管。

    approval_view 是 L3 全员基线码，不再作为「可看任意单据」的兜底：
    详情与附件下载都改为按参与关系判定，避免全员横向越权。
    """
    if user.is_superuser:
        return True
    if approval.applicant_id == user.pk or approval.approver_id == user.pk:
        return True
    if approval.signers.filter(signer=user).exists():
        return True
    return approval.cc_users.filter(pk=user.pk).exists()


def _can_act(user, approval):
    """审批操作人校验（v1.5.17：仅待审批可操作，处理后不可修改）：
    - 会签单：必须是会签人本人且未签
    - 普通单：审批人本人 或 超级管理员（v1.7.1 / P0-10：去掉 approval_approve 全局旁路）
    """
    if approval.status != Approval.Status.PENDING:
        return False
    if approval.is_counter_signature():
        row = approval.signers.filter(signer=user).first()
        return row is not None and not row.signed
    if approval.approver_id is None:
        return False
    return user == approval.approver or user.is_superuser


def _departments():
    """跨插件零 import：动态取 user.Department；插件停用时降级为空。"""
    try:
        Department = dj_apps.get_model('user', 'Department')
    except LookupError:
        return []
    return Department.objects.filter(is_active=True).order_by('name')


def _overtime_choices(user):
    """调休依据：本人近一年已通过的加班审批（v1.7.1 / P1-25）。

    只认 APPROVED：草稿 / 待审批 / 已驳回的加班都不能作为调休依据；
    created_at 限近 365 天，避免陈年加班被反复使用。
    """
    since = timezone.now() - timedelta(days=365)
    rows = Approval.objects.filter(
        applicant=user, approval_type=Approval.Type.OVERTIME,
        status=Approval.Status.APPROVED, created_at__gte=since,
    ).order_by('-created_at')[:50]
    choices = []
    for row in rows:
        start = row.form_data.get('start_time', '')
        end = row.form_data.get('end_time', '')
        label = f'#{row.pk} {start} ~ {end}' if start or end else f'#{row.pk} {row.title}'
        choices.append((str(row.pk), label))
    return choices


def _fallback_approvers(applicant):
    """路由缺失时的审批人候选（v1.5.18）：申请人直属上级 + 具备审批权限的启用用户。"""
    candidates = []
    leader = applicant.leader if applicant.leader_id else None
    if leader is not None and leader.is_active and leader.pk != applicant.pk:
        candidates.append(leader)
    for user in User.objects.filter(is_active=True).exclude(pk=applicant.pk).order_by('pk'):
        if user.has_perm('approval_approve') and user not in candidates:
            candidates.append(user)
    return candidates


def _summary(approval_type, cleaned, basis_label=''):
    """把动态字段拼成 human-readable 内容（同时保留原始 form_data）。"""
    lines = []
    for name, label in forms.type_fields(approval_type):
        value = cleaned.get(name)
        if value in (None, ''):
            continue
        if name == 'basis' and basis_label:
            value = basis_label
        value = getattr(value, 'name', value)   # 上传文件只展示文件名
        lines.append(f'{label}：{value}')
    return '\n'.join(lines)


@require_perm('approval_view')
def approval_list(request):
    """我发起的审批（v1.5.16：已驳回且申请人隐藏的记录不再展示）。"""
    approvals = (
        Approval.objects
        .filter(applicant=request.user, applicant_hidden=False)
        .select_related('applicant', 'approver')
    )
    page_obj = Paginator(approvals, LIST_PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'approval/approval_list.html', {
        'approvals': page_obj,
        'page_obj': page_obj,
        'total': page_obj.paginator.count,
    })


@require_perm('approval_approve')
def approval_pending(request):
    """待我审批：普通单（approver=我） + 会签单（我是 signer 且未签）。

    v1.5.15：仅具备 approval_approve 的管理岗可见（L3 隐藏入口与页面）。
    v1.7.1（P1-20）：两个查询集合并后再分页，避免只分页其中一半。
    """
    approvals = Approval.objects.filter(
        approver=request.user, status=Approval.Status.PENDING,
    ).select_related('applicant', 'approver')
    counter = Approval.objects.filter(
        status=Approval.Status.PENDING,
        signers__signer=request.user, signers__signed=False,
    ).select_related('applicant', 'approver')
    merged = list(approvals) + [a for a in counter if a not in approvals]
    page_obj = Paginator(merged, LIST_PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'approval/approval_pending.html', {
        'approvals': page_obj,
        'page_obj': page_obj,
        'total': len(merged),
    })


@require_perm('approval_approve')
def approval_cc(request):
    """抄送我的（v1.5.17：仅管理岗可见，L3 隐藏）。"""
    approvals = request.user.cc_approvals.select_related(
        'applicant', 'approver').order_by('-created_at')
    page_obj = Paginator(approvals, LIST_PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'approval/approval_cc.html', {
        'approvals': page_obj,
        'page_obj': page_obj,
        'total': page_obj.paginator.count,
    })


@require_perm('approval_view')
def approval_create(request):
    """发起审批 / 重新申请（v1.5.17：重新申请进入预填的可编辑表单）。"""
    reapply_of = request.GET.get('reapply') or request.POST.get('reapply_of')
    source = None
    if reapply_of:
        source = Approval.objects.filter(
            pk=reapply_of, applicant=request.user,
            status=Approval.Status.REJECTED).first()
        if source is None:
            return redirect('approval:approval_list')

    type_key = (source.approval_type if source else (
        request.GET.get('type') or request.POST.get('approval_type')
        or Approval.Type.LEAVE))
    if type_key not in forms.FORM_CLASSES:
        type_key = Approval.Type.LEAVE

    departments = _departments()
    # v1.5.18：审批人限定为该类审批的相关业务负责人；无路由部门时回退直属上级 / 审批权限用户
    approvers = [u for u in resolve_candidates(type_key)
                 if u.pk != request.user.pk]
    if not approvers:
        approvers = _fallback_approvers(request.user)
    overtime_choices = _overtime_choices(request.user)
    initial = dict(source.form_data) if source else None
    form = forms.form_for_type(
        type_key, request.POST or None, request.FILES or None,
        applicant=request.user,
        departments=departments, approvers=approvers,
        overtime_choices=overtime_choices, initial=initial)
    if approvers:
        form.fields['approver'].initial = str(approvers[0].pk)
    if source is not None and source.department_id:
        form.fields['department'].initial = str(source.department_id)

    if request.method == 'POST' and form.is_valid():
        Department = None
        if departments:
            Department = departments.model
        department = None
        if Department is not None:
            department = Department.objects.filter(
                pk=form.cleaned_data['department']).first()
        approver = User.objects.filter(
            pk=form.cleaned_data.get('approver'), is_active=True).first()
        if department is None:
            form.add_error('department', '请选择有效部门')
        elif approver is None:
            form.add_error('approver', '请选择有效的业务负责人')
        else:
            form_data = {}
            for name, _label in forms.type_fields(type_key):
                value = form.cleaned_data.get(name)
                if value in (None, ''):
                    continue
                form_data[name] = getattr(value, 'name', str(value))
            basis_id = form_data.get('basis')
            basis_label = ''
            if basis_id:
                basis_label = dict(overtime_choices).get(str(basis_id), '')
                if basis_label:
                    form_data['basis_label'] = basis_label
            # v1.7.1（P1-19）：建单 → 提交 → 替换原单 放在同一事务里；
            # 原单加行锁并二次校验，双击 / 并发重复提交只会生成一张新单。
            with transaction.atomic():
                locked_source = None
                if source is not None:
                    locked_source = Approval.objects.select_for_update().get(pk=source.pk)
                    if (locked_source.status != Approval.Status.REJECTED
                            or locked_source.replaced_by_id is not None):
                        return redirect('approval:approval_list')
                approval = Approval.objects.create(
                    approval_type=type_key,
                    title=f'{Approval.Type(type_key).label}｜{request.user.last_name or request.user.username}',
                    content=_summary(type_key, form.cleaned_data, basis_label),
                    applicant=request.user,
                    approver=approver,
                    department_id=department.pk,
                    department_name=department.name,
                    form_data=form_data,
                    amount=form.cleaned_data.get('amount') if type_key == Approval.Type.EXPENSE else None,
                    attachment=form.cleaned_data.get('seal_file') if type_key == Approval.Type.SEAL else None)
                submit(approval, request.user,
                       f'重新申请（原单 #{locked_source.pk}）' if locked_source else '发起审批',
                       action='resubmit' if locked_source else 'submit')
                if locked_source is not None:
                    locked_source.replaced_by = approval
                    locked_source.applicant_hidden = True
                    locked_source.save(
                        update_fields=['replaced_by', 'applicant_hidden', 'updated_at'])
                    ApprovalRecord.objects.create(
                        approval=locked_source, operator=request.user, action='replaced',
                        comment=f'被 #{approval.pk} 替换')
                    return redirect('approval:approval_detail', approval_id=approval.pk)
            return redirect('approval:approval_list')

    return render(request, 'approval/approval_form.html', {
        'form': form,
        'type_key': type_key,
        'types': [{'key': key, 'label': Approval.Type(key).label}
                  for key in forms.FORM_TYPES],
        'users': approvers,
        'reapply_of': source,
    })


@require_perm('approval_view')
@require_POST
def approval_hide(request, approval_id):
    """删除申请记录（v1.5.16）：仅对申请人隐藏，不删除审批留痕。"""
    approval = get_object_or_404(Approval, pk=approval_id, applicant=request.user)
    if approval.status == Approval.Status.REJECTED:
        approval.applicant_hidden = True
        approval.save(update_fields=['applicant_hidden', 'updated_at'])
    return redirect('approval:approval_list')


@login_required
def approval_detail(request, approval_id):
    """审批详情 + 通过/驳回（普通） + 会签通过/驳回（会签单）。"""
    approval = get_object_or_404(Approval, pk=approval_id)
    if not _may_view(request.user, approval):
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
        except (ValueError, PermissionError):
            # 非法流转 / 非本人审批：静默回到详情（状态未变，前端二次确认已提示）
            pass
        return redirect('approval:approval_detail', approval_id=approval.id)

    form_rows = []
    for name, label in forms.type_fields(approval.approval_type):
        value = approval.form_data.get(name, '')
        if name == 'basis':
            value = approval.form_data.get('basis_label', value)
        if value in (None, '', '—'):   # v1.5.17：详情隐藏空内容项
            continue
        form_rows.append((label, value))

    return render(request, 'approval/approval_detail.html', {
        'approval': approval,
        'records': approval.records.all(),
        'signers': approval.signers.all(),
        'can_act': _can_act(request.user, approval),
        'is_counter': approval.is_counter_signature(),
        'form_rows': form_rows,
        'cc_users': approval.cc_users.all(),
        'status_pending': approval.status == Approval.Status.PENDING,
    })


@login_required
def approval_attachment(request, approval_id):
    """用章附件下载（v1.5.14）：仅单据相关人 / 超管可下载（v1.7.1 / P0-9）。

    approval_view 是 L3 全员基线码，不能作为附件可见性兜底，否则任一员工
    改 URL 里的 id 即可下载他人用章文件。
    """
    approval = get_object_or_404(Approval, pk=approval_id)
    if not _may_view(request.user, approval):
        return redirect('index')
    if not approval.attachment:
        return redirect('approval:approval_detail', approval_id=approval.id)
    return FileResponse(
        approval.attachment.open('rb'), as_attachment=True,
        filename=approval.attachment.name.rsplit('/', 1)[-1])
