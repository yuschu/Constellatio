"""user 插件视图：部门 / 用户 / 角色管理（RBAC，权限码 user_manage）。

v1.2：
- 部门：新增/修改（即时生效+上链）；软删（is_active=False，即时+上链）；
        硬删（物理删除）需发起部门删除审批单，会签全部通过后执行物理删除+上链
- 用户状态机：启用 / 禁用（admin 直接禁用；普通管理员走会签审批）/ 冻结权限 / 解冻
- 密码二次确认（表单层）；超管 L0 最高，操作目标为超管一律拒绝
"""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from plugin_host.pagination import paginate
from plugin_host.permissions import require_perm
from plugin_host.signals import (
    dept_delete_requested,
    dept_disabled,
    dept_updated,
    password_changed,
    user_created,
    user_disabled,
    user_status_changed,
    user_updated,
)

from . import services
from .forms import DepartmentForm, PasswordForm, ProfileForm, RoleForm, UserForm
from .models import Department, Role, User
from .perms import BASELINE_PERMS, LEVEL_LABELS, user_level


def _clean_multi(post, field):
    """多选字段（M2M）空值清洗：过滤空字符串选项，避免校验报错。"""
    data = post.copy()
    values = [v for v in data.getlist(field) if v]
    if values:
        data.setlist(field, values)
    else:
        data.pop(field, None)
    return data


def _effective_permissions(user):
    """用户的有效权限：超管全部；否则个人权限 + 角色权限去重。"""
    if user.is_superuser:
        return Permission.objects.select_related('content_type')
    ids = set(user.user_permissions.values_list('pk', flat=True))
    for role in user.roles.all():
        ids.update(role.permissions.values_list('pk', flat=True))
    return Permission.objects.filter(pk__in=ids).select_related('content_type')


def _guard_superuser(request, target):
    """权限层级：超管 L0 最高，其他任何用户不能对超管操作（判定口径在 services 里唯一）。"""
    return not services.can_change_status(request.user, target)


# ---------------------------------------------------------------------------
# 部门
# ---------------------------------------------------------------------------
def _render_department_page(request, form=None, edit_dept=None, error='', form_open=False):
    """部门页的唯一渲染入口（列表 + 部门表单设置弹层）。

    v2.1.2：新建走二级页，形态照 DSH 点开设置的那一页 —— 遮罩 + 800×800 面板
    （title / options），由 user/department_list.html 里的 `#ds-dept-form` 弹层承载。
    v2.1.5：修改也并进同一块弹层（`?view=edit&id=<pk>`），正文与新建共用
    `user/_department_form_body.html`，两种模式只差标题与提交文案；列表行内不再
    展开右侧常驻的「修改部门」卡片。`?view=new` / `?view=edit` / 校验失败时
    `form_open=True`，页面一次渲染完，弹层只是盖在列表上。
    """
    departments = paginate(request, Department.objects.all().order_by('id'))
    list_url = reverse('user:department_list')
    if edit_dept is not None:
        mode = 'edit'
        form_title = _('修改部门：%(name)s') % {'name': edit_dept.name}
        form_query = f'view=edit&id={edit_dept.pk}'
        submit_label = _('保存修改')
        default_form = DepartmentForm(instance=edit_dept)
    else:
        mode = 'create'
        form_title = _('新建部门')
        form_query = 'view=new'
        submit_label = _('创建')
        default_form = DepartmentForm()
    return render(request, 'user/department_list.html', {
        'page_obj': departments,
        'form': form if form is not None else default_form,
        'edit_dept': edit_dept,
        'dept_form_open': form_open,
        'dept_form_mode': mode,
        'dept_form_title': form_title,
        'dept_form_query': form_query,
        'dept_form_url': f'{list_url}?{form_query}',
        'dept_form_submit': submit_label,
        'dept_new_url': f'{list_url}?view=new',
        'dept_edit_url': f'{list_url}?view=edit&id=',
        'dept_list_url': list_url,
        'error': error,
    })


@require_perm('user_manage')
def department_list(request):
    """部门列表 + 新建 + 修改 + 软删（停用）+ 硬删请求（会签审批）。

    v2.1.2：新建不再占用列表右侧的常驻卡片，改成部门页的二级弹层
    （`?view=new` 打开，形态照 DSH 点开设置的那一页），列表页只留列表。
    v2.1.5：修改同样走这块弹层（`?view=edit&id=<pk>`）。弹层表单的 action 为空
    → POST 回本页，按 `?view=` 分派到创建 / 修改；校验失败就地渲染回弹层。
    """
    view = request.GET.get('view')
    if request.method == 'POST':
        action = request.POST.get('action', 'create')
        if action == 'create':
            return _save_department_create(request)
        elif action == 'edit':
            # dept_id 优先取表单隐藏字段；表单没带（或走的是深链页的原地提交）时
            # 回落到地址里的 ?id=，与用户 / 角色的分派口径一致。
            return _save_department_edit(
                request, request.POST.get('dept_id') or request.GET.get('id'))
        elif action == 'soft_delete':
            dept_id = request.POST.get('dept_id')
            dept = get_object_or_404(Department, pk=dept_id)
            if dept.is_active:
                dept.is_active = False
                dept.save(update_fields=['is_active', 'updated_at'])
                dept_disabled.send(sender=Department, dept_id=dept.pk, operator_id=request.user.pk)
            return redirect('user:department_list')
        elif action == 'hard_delete':
            dept_id = request.POST.get('dept_id')
            dept = get_object_or_404(Department, pk=dept_id)
            if dept.members.exists():
                return _render_department_page(
                    request,
                    error=f'部门「{dept.name}」仍有成员，不能直接物理删除；请先调整成员归属。')
            # 发起部门删除审批单（会签：全部具备 dept_delete_approve 权限的管理员）
            dept_delete_requested.send(
                sender=Department, dept_id=dept.pk, operator_id=request.user.pk,
                title=f'部门删除审批：{dept.name}',
                content=f'申请物理删除部门「{dept.name}」（ID:{dept.pk}），需全部审批人通过后执行。')
            return redirect('user:department_list')
        return _save_department_create(request)

    if view == 'edit':
        target = get_object_or_404(Department, pk=request.GET.get('id'))
        return _render_department_page(request, form_open=True, edit_dept=target)
    return _render_department_page(request, form_open=view == 'new')


def _save_department_create(request):
    """新建部门：校验 → 落库 → 回列表；校验失败渲染回弹层（create 模式）。"""
    form = DepartmentForm(request.POST)
    if form.is_valid():
        form.save()
        return redirect('user:department_list')
    return _render_department_page(request, form, form_open=True)


def _save_department_edit(request, dept_id):
    """修改部门：信号在保存后发；校验失败渲染回弹层（edit 模式）。"""
    dept = get_object_or_404(Department, pk=dept_id)
    form = DepartmentForm(request.POST, instance=dept)
    if form.is_valid():
        form.save()
        dept_updated.send(sender=Department, dept_id=dept.pk, operator_id=request.user.pk)
        return redirect('user:department_list')
    return _render_department_page(request, form, edit_dept=dept, form_open=True)


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
def _render_user_list(request, form=None, form_open=False, edit_user=None):
    """用户列表的唯一渲染入口（列表 + 用户表单设置弹层）。

    v2.1.3：新建 / 编辑都是 DSH 设置弹层形态（遮罩 + 800×800 面板），正文同一份
    `user/_user_form_body.html`，两种模式只差标题与提交文案：
    - create：`?view=new`；
    - edit：`?view=edit&id=<pk>`，行内「编辑」跳到这个 URL 打开弹层。
    弹层里的表单 action 为空 → POST 回列表页，`user_list` 按 `?view=` 分派到
    创建 / 编辑逻辑；校验失败也回到这里（form_open=True），一次渲染完。
    本页只有一个分区，所以面板带 ds-settings--single：不渲染左侧 188px
    分区列，内容与按钮居中。
    """
    users = paginate(
        request, User.objects.select_related('department').prefetch_related('roles').order_by('id'))
    list_url = reverse('user:user_list')
    if edit_user is not None:
        mode = 'edit'
        form_title = _('编辑用户：%(name)s') % {
            'name': edit_user.last_name or edit_user.username}
        form_query = f'view=edit&id={edit_user.pk}'
        submit_label = _('保存')
        default_form = UserForm(instance=edit_user)
    else:
        mode = 'create'
        form_title = _('新建用户')
        form_query = 'view=new'
        submit_label = _('创建')
        default_form = UserForm(operator=request.user)
    return render(request, 'user/user_list.html', {
        'page_obj': users,
        'form': form if form is not None else default_form,
        'user_form_open': form_open,
        'user_form_mode': mode,
        'user_form_title': form_title,
        'user_form_query': form_query,
        'user_form_url': f'{list_url}?{form_query}',
        'user_form_submit': submit_label,
        'user_create_url': f'{list_url}?view=new',
        'user_edit_url': f'{list_url}?view=edit&id=',
        'user_list_url': list_url,
    })


@require_perm('user_manage')
def user_list(request):
    # v1.7.6：用户列表分页（排序在分页之前定死）
    view = request.GET.get('view')
    if request.method == 'POST':
        # 弹层表单 POST 回本页：按 ?view= 分派，错误就地渲染回弹层。
        if view == 'edit':
            return _save_user_edit(request, request.GET.get('id'), host='list')
        return _save_user_create(request, host='list')
    if view == 'edit':
        target = get_object_or_404(User, pk=request.GET.get('id'))
        if _guard_superuser(request, target):
            return redirect('user:user_list')
        return _render_user_list(request, form_open=True, edit_user=target)
    return _render_user_list(request, form_open=view == 'new')


def _save_user_create(request, host='page'):
    """创建用户的校验与落库；`host` 决定校验失败回到列表弹层还是独立深链页。"""
    data = _clean_multi(_clean_multi(request.POST, 'roles'), 'user_permissions')
    form = UserForm(data, operator=request.user)
    if form.is_valid():
        user = form.save()
        user_created.send(sender=user.__class__, user_id=user.pk)
        return redirect('user:user_list')
    if host == 'list':
        # 校验失败留在设置弹层里，把错误挂回对应字段
        return _render_user_list(request, form, form_open=True)
    return render(request, 'user/user_create_page.html', {
        'form': form,
        'user_form_submit': _('创建'),
        'user_form_mode': 'create',
        'user_list_back': reverse('user:user_list'),
    })


@require_perm('user_manage')
def user_create(request):
    if request.method == 'POST':
        return _save_user_create(request, host='page')
    return render(request, 'user/user_create_page.html', {
        'form': UserForm(operator=request.user),
        'user_form_submit': _('创建'),
        'user_form_mode': 'create',
        'user_list_back': reverse('user:user_list'),
    })


def _save_user_edit(request, user_id, host='page'):
    """编辑用户的校验与落库（口径同 `_save_user_create` 的 host 分派）。"""
    user = get_object_or_404(User, pk=user_id)
    if _guard_superuser(request, user):
        return redirect('user:user_list')
    data = _clean_multi(_clean_multi(request.POST, 'roles'), 'user_permissions')
    form = UserForm(data, instance=user, operator=request.user)
    if form.is_valid():
        # v1.7.1（P0-11）：普通管理员不能借编辑页改 is_active 绕过「禁用需会签」，
        # 状态变更必须走 user_status（超管直接生效，其余人先冻结再发起会签）。
        if 'is_active' in form.changed_data and not request.user.is_superuser:
            form.add_error(
                'is_active',
                _('启用 / 禁用请使用状态操作：普通管理员禁用需会签审批'))
        else:
            pwd_changed = bool(form.cleaned_data.get('password'))
            status_changed = 'is_active' in form.changed_data
            form.save()
            if pwd_changed:
                from plugin_host.signals import password_changed
                password_changed.send(sender=user.__class__, user_id=user.pk,
                                      operator_id=request.user.pk)
            if status_changed:
                # 与 user_status 口径一致：禁用同时冻结权限，并留痕
                user.refresh_from_db()
                if not user.is_active:
                    user.permission_frozen = True
                    user.save(update_fields=['permission_frozen', 'updated_at'])
                    user_disabled.send(sender=User, user_id=user.pk,
                                       operator_id=request.user.pk)
                user_status_changed.send(
                    sender=User, user_id=user.pk,
                    status='enabled' if user.is_active else 'disabled',
                    operator_id=request.user.pk)
            user_updated.send(sender=user.__class__, user_id=user.pk)
            return redirect('user:user_list')
    if host == 'list':
        return _render_user_list(request, form, form_open=True, edit_user=user)
    return render(request, 'user/user_edit_page.html', {
        'form': form,
        'user_form_submit': _('保存'),
        'user_form_mode': 'edit',
        'user_form_title': _('编辑用户：%(name)s') % {
            'name': user.last_name or user.username},
        'user_list_back': reverse('user:user_list'),
    })


@require_perm('user_manage')
def user_edit(request, user_id):
    if request.method == 'POST':
        return _save_user_edit(request, user_id, host='page')
    user = get_object_or_404(User, pk=user_id)
    if _guard_superuser(request, user):
        return redirect('user:user_list')
    return render(request, 'user/user_edit_page.html', {
        'form': UserForm(instance=user),
        'user_form_submit': _('保存'),
        'user_form_mode': 'edit',
        'user_form_title': _('编辑用户：%(name)s') % {
            'name': user.last_name or user.username},
        'user_list_back': reverse('user:user_list'),
    })


@require_perm('user_manage')
def user_status(request, user_id):
    """用户状态操作：启用 / 禁用 / 冻结权限 / 解冻（业务规则在 services.change_status）。

    v1.7.14：状态机整体搬到 `plugins/user/services.py`，视图只做参数提取与响应；
    超管保护由 service 的 `can_change_status` 统一判定（越权直接调用会抛 StatusChangeDenied）。
    """
    target = get_object_or_404(User, pk=user_id)
    if not services.can_change_status(request.user, target):
        return redirect('user:user_list')
    services.change_status(request.user, target, request.POST.get('status'))
    return redirect('user:user_list')


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------
def _render_role_list(request, form=None, form_open=False, edit_role=None):
    """角色列表的唯一渲染入口（列表 + 角色表单设置弹层，口径同用户列表）。"""
    list_url = reverse('user:role_list')
    if edit_role is not None:
        mode = 'edit'
        form_title = _('编辑角色：%(name)s') % {'name': edit_role.name}
        form_query = f'view=edit&id={edit_role.pk}'
        submit_label = _('保存')
        default_form = RoleForm(instance=edit_role, operator=request.user)
    else:
        mode = 'create'
        form_title = _('新建角色')
        form_query = 'view=new'
        submit_label = _('创建')
        default_form = RoleForm(operator=request.user)
    return render(request, 'user/role_list.html', {
        'roles': Role.objects.prefetch_related('permissions').order_by('id'),
        'form': form if form is not None else default_form,
        'role_form_open': form_open,
        'role_form_mode': mode,
        'role_form_title': form_title,
        'role_form_query': form_query,
        'role_form_url': f'{list_url}?{form_query}',
        'role_form_submit': submit_label,
        'role_create_url': f'{list_url}?view=new',
        'role_edit_url': f'{list_url}?view=edit&id=',
        'role_list_url': list_url,
    })


@require_perm('user_manage')
def role_list(request):
    view = request.GET.get('view')
    if request.method == 'POST':
        if view == 'edit':
            return _save_role_edit(request, request.GET.get('id'), host='list')
        return _save_role_create(request, host='list')
    if view == 'edit':
        return _render_role_list(
            request, form_open=True,
            edit_role=get_object_or_404(Role, pk=request.GET.get('id')))
    return _render_role_list(request, form_open=view == 'new')


def _save_role_create(request, host='page'):
    form = RoleForm(_clean_multi(request.POST, 'permissions'), operator=request.user)
    if form.is_valid():
        form.save()
        return redirect('user:role_list')
    if host == 'list':
        return _render_role_list(request, form, form_open=True)
    return render(request, 'user/role_create_page.html', {
        'form': form,
        'role_form_submit': _('创建'),
        'role_form_mode': 'create',
        'role_list_back': reverse('user:role_list'),
    })


@require_perm('user_manage')
def role_create(request):
    if request.method == 'POST':
        return _save_role_create(request, host='page')
    return render(request, 'user/role_create_page.html', {
        'form': RoleForm(operator=request.user),
        'role_form_submit': _('创建'),
        'role_form_mode': 'create',
        'role_list_back': reverse('user:role_list'),
    })


def _save_role_edit(request, role_id, host='page'):
    role = get_object_or_404(Role, pk=role_id)
    form = RoleForm(_clean_multi(request.POST, 'permissions'),
                    instance=role, operator=request.user)
    if form.is_valid():
        form.save()
        return redirect('user:role_list')
    if host == 'list':
        return _render_role_list(request, form, form_open=True, edit_role=role)
    return render(request, 'user/role_edit_page.html', {
        'form': form,
        'role_form_submit': _('保存'),
        'role_form_mode': 'edit',
        'role_form_title': _('编辑角色：%(name)s') % {'name': role.name},
        'role_list_back': reverse('user:role_list'),
    })


@require_perm('user_manage')
def role_edit(request, role_id):
    if request.method == 'POST':
        return _save_role_edit(request, role_id, host='page')
    role = get_object_or_404(Role, pk=role_id)
    return render(request, 'user/role_edit_page.html', {
        'form': RoleForm(instance=role, operator=request.user),
        'role_form_submit': _('保存'),
        'role_form_mode': 'edit',
        'role_form_title': _('编辑角色：%(name)s') % {'name': role.name},
        'role_list_back': reverse('user:role_list'),
    })



# ---------------------------------------------------------------------------
# 个人中心
# ---------------------------------------------------------------------------
def _permission_profile_context(user):
    """个人中心权限上下文：角色 / 直接权限 / 有效权限 / 等级 / 全员基线。"""
    from django.contrib.auth.models import Permission
    baseline = Permission.objects.filter(codename__in=BASELINE_PERMS)
    return {
        'roles': user.roles.prefetch_related('permissions'),
        'direct_permissions': user.user_permissions.select_related('content_type'),
        'effective_permissions': _effective_permissions(user),
        'user_level': user_level(user),
        'user_level_label': LEVEL_LABELS[user_level(user)],
        'baseline_permissions': baseline,
        'is_frozen': user.permission_frozen,
    }


def _profile_context(request, view='', edit_form=None, password_form=None):
    """个人中心的一种上下文：主页正文 + 三个子设置弹层（编辑资料 / 权限 / 密码）。

    v2.1.3：个人中心与它的三个子页都改成设置面板形态。主页是 inline 面板，
    三个子页从主页里以弹层打开（`?view=edit|perms|password`），提交失败时把
    绑定错误的表单交回这里，弹层保持打开并显示字段错误。
    """
    context = _permission_profile_context(request.user)
    context.update({
        'profile_view': view,
        'profile_edit_form': edit_form if edit_form is not None else ProfileForm(
            instance=request.user),
        'profile_password_form': password_form if password_form is not None else PasswordForm(
            user=request.user),
        'profile_edit_url': reverse('user:profile_edit'),
        'profile_perms_url': reverse('user:profile_permissions'),
        'profile_password_url': reverse('user:profile_password'),
        'profile_url': reverse('user:profile'),
        # 弹层开合对应的查询参数（地址栏是唯一真源）
        'profile_edit_open': view == 'edit',
        'profile_perms_open': view == 'perms',
        'profile_password_open': view == 'password',
    })
    return context


def _profile_saved_redirect(request):
    """资料 / 密码保存成功后的落点。

    v2.1.6：个人资料从设置面板里原地打开（不再是「跳个人中心页」），所以保存后
    优先回到打开它的那一页（`next` 由 ds-shell.js 填成进面板前的地址）；没有
    `next`（例如直接访问深链页提交）仍回个人中心，保持旧口径。
    """
    nxt = request.POST.get('next') or ''
    if nxt and url_has_allowed_host_and_scheme(
            nxt, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return redirect(nxt)
    return redirect('user:profile')


@login_required
def profile(request):
    """个人中心：资料摘要 + 权限入口 + 修改密码入口（设置面板形态）。"""
    view = request.GET.get('view') or ''
    if view not in ('edit', 'perms', 'password'):
        view = ''
    return render(request, 'user/profile.html', _profile_context(request, view))


@login_required
def profile_edit(request):
    """编辑自己的资料：只允许姓名 / 邮箱，不触碰角色与权限。"""
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            user_updated.send(sender=request.user.__class__, user_id=request.user.pk)
            return _profile_saved_redirect(request)
        # 校验失败：把带错的面板原样交回（在设置里原地打开时，错误直接落在面板里）
        return render(request, 'user/profile_edit.html',
                      _profile_context(request, edit_form=form))
    return render(request, 'user/profile_edit.html', _profile_context(request))


@login_required
def profile_permissions(request):
    """查看自己的角色、直接权限、有效权限、等级与全员基线权限。"""
    return render(request, 'user/profile_permissions.html',
                  _profile_context(request))


@login_required
def profile_password(request):
    """修改自己的密码：验证旧密码、二次确认、更新会话、发信号。"""
    if request.method == 'POST':
        form = PasswordForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password'])
            request.user.save(update_fields=['password'])
            update_session_auth_hash(request, request.user)
            password_changed.send(sender=request.user.__class__,
                                  user_id=request.user.pk, operator_id=request.user.pk)
            return _profile_saved_redirect(request)
        return render(request, 'user/profile_password.html',
                      _profile_context(request, password_form=form))
    return render(request, 'user/profile_password.html', _profile_context(request))
