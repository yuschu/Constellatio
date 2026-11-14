"""approval 插件视图：发起 / 我的审批 / 待我审批 / 抄送我的 / 详情操作。"""

from datetime import timedelta

from django.apps import apps as dj_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from plugin_host.exceptions import ObjectPermissionDenied
from plugin_host.pagination import DEFAULT_PAGE_SIZE, paginate
from plugin_host.permissions import require_perm

from . import forms, services
from .models import Approval, ApprovalRecord
from .routing import candidate_approvers as resolve_candidates
from .services import approve, reject, sign_approve, sign_reject, submit

User = get_user_model()

# 与 assistant 的 session 交接契约：assistant 只放草稿，不建 Approval；
# 这里只读草稿预填表单，提交仍走本视图的真实 POST。
ASSISTANT_DRAFT_SESSION_KEY = 'assistant_approval_drafts'

# v1.7.1（P1-20）：列表统一分页；v1.7.6 改为引用容器常量，避免各插件各写一个数字
LIST_PAGE_SIZE = DEFAULT_PAGE_SIZE


def _may_view(user, approval):
    """对象级可见性（v1.7.14：口径在 services.may_view，这里保留薄壳给既有调用点）。"""
    return services.may_view(user, approval)


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


def _assistant_draft(request):
    """取 session 里的助手草稿；token 只在当前用户会话内有效。"""
    token = request.GET.get('draft') or request.POST.get('draft')
    if not token:
        return None, None
    records = request.session.get(ASSISTANT_DRAFT_SESSION_KEY) or {}
    if not isinstance(records, dict):
        return None, None
    record = records.get(token)
    if not isinstance(record, dict) or record.get('user_id') != request.user.pk:
        return None, None
    draft = record.get('draft')
    if (not isinstance(draft, dict)
            or draft.get('approval_type') not in (Approval.Type.LEAVE, Approval.Type.EXPENSE)
            or not isinstance(draft.get('initial'), dict)):
        return None, None
    return token, draft


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


def _approval_list_context(request):
    """我发起的审批（v1.5.16：已驳回且申请人隐藏的记录不再展示）。"""
    approvals = (
        Approval.objects
        .filter(applicant=request.user, applicant_hidden=False)
        .select_related('applicant', 'approver')
        # v1.7.6：分页前定死顺序，补唯一键 tiebreaker，避免同一秒创建的记录翻页重复/漏行
        .order_by('-created_at', '-id')
    )
    page_obj = paginate(request, approvals, LIST_PAGE_SIZE)
    return {'approvals': page_obj, 'page_obj': page_obj, 'total': page_obj.paginator.count}


def _create_context(request, form=None, type_key=None, source=None, chip_prefix='?type='):
    """发起审批的设置页上下文（列表弹层与独立深链页同一口径）。

    v2.1.3：发起审批改 DSH 设置弹层形态。列表页里的弹层用 `?view=new` 打开，
    类型 chips 的 href 因此是 `?view=new&type=…`（chip_prefix），切类型不会
    把弹层丢掉；独立深链 /approval/new/ 用 `?type=…`。
    """
    type_key = type_key or request.GET.get('type') or Approval.Type.LEAVE
    if type_key not in forms.FORM_CLASSES:
        type_key = Approval.Type.LEAVE

    departments = _departments()
    approvers = [u for u in resolve_candidates(type_key) if u.pk != request.user.pk]
    if not approvers:
        approvers = _fallback_approvers(request.user)
    if form is None:
        form = forms.form_for_type(
            type_key, None, None, applicant=request.user,
            departments=departments, approvers=approvers,
            overtime_choices=_overtime_choices(request.user))
        if approvers:
            form.fields['approver'].initial = str(approvers[0].pk)
    return {
        'form': form,
        'type_key': type_key,
        'users': approvers,
        'reapply_of': source,
        # 助手草稿的 session token 随表单回传，成功建单后由 approval_create 清掉；
        # 不是助手来源时为空，不影响原表单。
        'assistant_draft_token': request.GET.get('draft') or request.POST.get('draft'),
        'type_chips': [
            {'key': key, 'label': Approval.Type(key).label,
             'href': f'{chip_prefix}{key}', 'active': key == type_key}
            for key in forms.FORM_TYPES
        ],
    }


@require_perm('approval_view')
def approval_list(request):
    # 弹层里的表单 action 为空 → POST 回到本页，这里分派给 approval_create：
    # 校验失败时它渲染回列表（弹层保持打开），成功则 PRG。
    if request.method == 'POST':
        return approval_create(request)
    ctx = _approval_list_context(request)
    if request.user.has_perm('approval_view'):
        list_url = reverse('approval:approval_list')
        ctx.update(_create_context(
            request, chip_prefix=f'{list_url}?view=new&type='))
        ctx.update({
            'create_open': request.method == 'GET' and request.GET.get('view') == 'new',
            'create_url': f'{list_url}?view=new',
            'approval_list_url': list_url,
        })
    return render(request, 'approval/approval_list.html', ctx)


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
    page_obj = paginate(request, merged, LIST_PAGE_SIZE)
    return render(request, 'approval/approval_pending.html', {
        'approvals': page_obj,
        'page_obj': page_obj,
        'total': len(merged),
    })


@require_perm('approval_approve')
def approval_cc(request):
    """抄送我的（v1.5.17：仅管理岗可见，L3 隐藏）。"""
    approvals = request.user.cc_approvals.select_related(
        'applicant', 'approver').order_by('-created_at', '-id')
    page_obj = paginate(request, approvals, LIST_PAGE_SIZE)
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

    draft_token, assistant_draft = _assistant_draft(request)
    type_key = (source.approval_type if source else (
        request.GET.get('type') or request.POST.get('approval_type')
        or (assistant_draft or {}).get('approval_type')
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
    if (source is None and assistant_draft
            and assistant_draft.get('approval_type') == type_key):
        initial = dict(assistant_draft.get('initial') or {})
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
                    amount=form.cleaned_data.get('amount') if type_key == Approval.Type.EXPENSE else None)
                if type_key == Approval.Type.SEAL:
                    # v1.7.14：落盘与校验在 services（建单仍在同一事务内）
                    services.store_attachment(approval, form.cleaned_data.get('seal_file'))
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
            if draft_token:
                records = request.session.get(ASSISTANT_DRAFT_SESSION_KEY) or {}
                if isinstance(records, dict):
                    records.pop(draft_token, None)
                    request.session[ASSISTANT_DRAFT_SESSION_KEY] = records
            return redirect('approval:approval_list')

    if source is not None:
        # 重新申请带原单信息，仍走独立页（不塞进列表弹层）
        ctx = _create_context(request, form=form, type_key=type_key, source=source)
        ctx['back_url'] = reverse('approval:approval_list')
        return render(request, 'approval/approval_form.html', ctx)

    if request.method == 'POST':
        # 校验失败：留在审批中心的设置弹层里，把错误挂回字段
        list_url = reverse('approval:approval_list')
        ctx = _approval_list_context(request)
        ctx.update(_create_context(
            request, form=form, type_key=type_key,
            chip_prefix=f'{list_url}?view=new&type='))
        ctx.update({
            'create_open': True,
            'create_url': f'{list_url}?view=new',
            'approval_list_url': list_url,
        })
        return render(request, 'approval/approval_list.html', ctx)

    ctx = _create_context(request, form=form, type_key=type_key)
    ctx['back_url'] = reverse('approval:approval_list')
    return render(request, 'approval/approval_form.html', ctx)


@require_perm('approval_view')
@require_POST
def approval_hide(request, approval_id):
    """删除申请记录（v1.5.16）：仅对申请人隐藏，不删除审批留痕。"""
    # v1.7.10：拆开「不存在」与「不是我的」——查不到仍 404，不是本人改 403，
    # 不再把两种情况并成一个 404（否则系统里又出现第三种越权反馈）。
    approval = get_object_or_404(Approval, pk=approval_id)
    if approval.applicant_id != request.user.pk:
        raise ObjectPermissionDenied('该审批单不属于你')
    if approval.status == Approval.Status.REJECTED:
        approval.applicant_hidden = True
        approval.save(update_fields=['applicant_hidden', 'updated_at'])
    return redirect('approval:approval_list')


@login_required
def approval_detail(request, approval_id):
    """审批详情 + 通过/驳回（普通） + 会签通过/驳回（会签单）。"""
    approval = get_object_or_404(Approval, pk=approval_id)
    if not _may_view(request.user, approval):
        # v1.7.10：对象级越权 → 403（原来 302 回工作台）；message 只进 JSON/日志
        raise ObjectPermissionDenied('该审批单不属于你')

    if request.method == 'POST':
        if not _can_act(request.user, approval):
            raise ObjectPermissionDenied('你无权审批该单据')
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
            # 状态已变（如刚被别人批过）等流转竞态：静默回到详情，前端二次确认已提示
            pass
        except PermissionError as exc:
            # services 的「不是审批人」理论上已被上面的 _can_act 拦住，但不可达分支也绝不能
            # 静默吞掉：并发/会签逻辑一旦演进到可达，必须看得见（禁止 try/except 吞异常）。
            raise ObjectPermissionDenied('你无权审批该单据') from exc
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
        'back_url': reverse('approval:approval_list'),
    })


@login_required
def approval_attachment(request, approval_id):
    """用章附件下载：鉴权与取文件句柄在 `services.attachment_for`（v1.7.14）。

    approval_view 是 L3 全员基线码，不能作为附件可见性兜底，否则任一员工
    改 URL 里的 id 即可下载他人用章文件（v1.7.1 / P0-9）。
    """
    approval = get_object_or_404(Approval, pk=approval_id)
    handle = services.attachment_for(request.user, approval)
    if handle is None:
        return redirect('approval:approval_detail', approval_id=approval.id)
    return FileResponse(
        handle, as_attachment=True,
        filename=approval.attachment.name.rsplit('/', 1)[-1])
