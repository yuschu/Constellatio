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
def _render_department_page(request, form=None, dept_id=None, error='', form_open=False):
    """部门页的唯一渲染入口（列表 + 「新建」设置弹层）。

    v2.1.2：新建走二级页，形态照 DSH 点开设置的那一页 —— 遮罩 + 800×800 面板
    （title / header / nav 188px / options），由 user/department_list.html 里的
    `#ds-dept-new` 弹层承载。`?view=new` 或表单校验失败时 `form_open=True`，
    页面一次渲染完，弹层只是盖在列表上，不再换模板、不再走第二套版式。
    """
    departments = paginate(request, Department.objects.all().order_by('id'))
    list_url = reverse('user:department_list')
    return render(request, 'user/department_list.html', {
        'page_obj': departments,
        'form': form if form is not None else DepartmentForm(),
        'dept_id': dept_id,
        'edit_dept': Department.objects.filter(pk=dept_id).first() if dept_id else None,
        'error': error,
        'dept_form_open': form_open,
        'dept_new_url': f'{list_url}?view=new',
        'dept_list_url': list_url,
    })


@require_perm('user_manage')
def department_list(request):
    """部门列表 + 新建 + 修改 + 软删（停用）+ 硬删请求（会签审批）。

    v2.1.2：新建不再占用列表右侧的常驻卡片，改成部门页的二级弹层
    （`?view=new` 打开，形态照 DSH 点开设置的那一页），列表页只留列表。
    """
    if request.method == 'GET' and request.GET.get('view') == 'new':
        return _render_department_page(request, DepartmentForm(), form_open=True)
    if request.method == 'POST':
        action = request.POST.get('action', 'create')
        if action == 'create':
            form = DepartmentForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('user:department_list')
            # 校验失败留在弹层里，把错误挂在对应字段上
            return _render_department_page(request, form, form_open=True)
        elif action == 'edit':
            dept_id = request.POST.get('dept_id')
            dept = get_object_or_404(Department, pk=dept_id)
            form = DepartmentForm(request.POST, instance=dept)
            if form.is_valid():
                form.save()
                dept_updated.send(sender=Department, dept_id=dept.pk, operator_id=request.user.pk)
                return redirect('user:department_list')
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
        else:
            dept_id = None
            form = DepartmentForm()
    else:
        form = DepartmentForm()
        dept_id = None

    return _render_department_page(request, form, dept_id)


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
def _render_user_list(request, form=None, form_open=False):
    """用户列表的唯一渲染入口（列表 + 「新建用户」设置弹层）。

    v2.1.3：新建改 DSH 设置弹层形态（遮罩 + 800×800 面板）。列表页里的入口是
    `?view=new` 打开弹层，校验失败也回到这里（form_open=True），一次渲染完；
    独立深链 /users/new/ 用同一块面板的无遮罩版本（user_create_page.html）。
    本页只有一个分区，所以面板带 ds-settings--single：不渲染左侧 188px
    分区列，内容与按钮居中。
    """
    users = paginate(
        request, User.objects.select_related('department').prefetch_related('roles').order_by('id'))
    list_url = reverse('user:user_list')
    return render(request, 'user/user_list.html', {
        'page_obj': users,
        'form': form if form is not None else UserForm(operator=request.user),
        'user_form_open': form_open,
        'user_create_url': f'{list_url}?view=new',
        'user_list_url': list_url,
    })


@require_perm('user_manage')
def user_list(request):
    # v1.7.6：用户列表分页（排序在分页之前定死）
    return _render_user_list(
        request, form_open=request.method == 'GET' and request.GET.get('view') == 'new')


@require_perm('user_manage')
def user_create(request):
    if request.method == 'POST':
        data = _clean_multi(_clean_multi(request.POST, 'roles'), 'user_permissions')
        form = UserForm(data, operator=request.user)
        if form.is_valid():
            user = form.save()
            user_created.send(sender=user.__class__, user_id=user.pk)
            return redirect('user:user_list')
        # 校验失败留在设置弹层里，把错误挂回对应字段
        return _render_user_list(request, form, form_open=True)
    return render(request, 'user/user_create_page.html', {
        'form': UserForm(operator=request.user),
        'user_list_back': reverse('user:user_list'),
    })


@require_perm('user_manage')
def user_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if _guard_superuser(request, user):
        return redirect('user:user_list')
    if request.method == 'POST':
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
    else:
        form = UserForm(instance=user)
    return render(request, 'user/user_form.html',
                  {'form': form, 'title': _('编辑用户：%(name)s') % {
                      'name': user.last_name or user.username}})


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
def _render_role_list(request, form=None, form_open=False):
    """角色列表的唯一渲染入口（列表 + 「新建角色」设置弹层，口径同用户列表）。"""
    list_url = reverse('user:role_list')
    return render(request, 'user/role_list.html', {
        'roles': Role.objects.prefetch_related('permissions').order_by('id'),
        'form': form if form is not None else RoleForm(operator=request.user),
        'role_form_open': form_open,
        'role_create_url': f'{list_url}?view=new',
        'role_list_url': list_url,
    })


@require_perm('user_manage')
def role_list(request):
    return _render_role_list(
        request, form_open=request.method == 'GET' and request.GET.get('view') == 'new')


@require_perm('user_manage')
def role_create(request):
    if request.method == 'POST':
        form = RoleForm(_clean_multi(request.POST, 'permissions'), operator=request.user)
        if form.is_valid():
            form.save()
            return redirect('user:role_list')
        return _render_role_list(request, form, form_open=True)
    return render(request, 'user/role_create_page.html', {
        'form': RoleForm(operator=request.user),
        'role_list_back': reverse('user:role_list'),
    })


@require_perm('user_manage')
def role_edit(request, role_id):
    role = get_object_or_404(Role, pk=role_id)
    if request.method == 'POST':
        form = RoleForm(_clean_multi(request.POST, 'permissions'),
                        instance=role, operator=request.user)
        if form.is_valid():
            form.save()
            return redirect('user:role_list')
    else:
        form = RoleForm(instance=role, operator=request.user)
    return render(request, 'user/role_form.html', {'form': form, 'title': _('编辑角色：%(name)s') % {'name': role.name}})



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


@login_required
def profile(request):
    """个人中心：资料摘要 + 权限入口 + 修改密码入口。"""
    return render(request, 'user/profile.html', _permission_profile_context(request.user))


@login_required
def profile_edit(request):
    """编辑自己的资料：只允许姓名 / 邮箱，不触碰角色与权限。"""
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            user_updated.send(sender=request.user.__class__, user_id=request.user.pk)
            return redirect('user:profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'user/profile_edit.html', {'form': form})


@login_required
def profile_permissions(request):
    """查看自己的角色、直接权限、有效权限、等级与全员基线权限。"""
    return render(request, 'user/profile_permissions.html',
                  _permission_profile_context(request.user))


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
            return redirect('user:profile')
    else:
        form = PasswordForm(user=request.user)
    return render(request, 'user/profile_password.html', {'form': form})
