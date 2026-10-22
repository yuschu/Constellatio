"""user 插件视图：部门 / 用户 / 角色管理（RBAC，权限码 user_manage）。

v1.2：
- 部门：新增/修改（即时生效+上链）；软删（is_active=False，即时+上链）；
        硬删（物理删除）需发起部门删除审批单，会签全部通过后执行物理删除+上链
- 用户状态机：启用 / 禁用（admin 直接禁用；普通管理员走会签审批）/ 冻结权限 / 解冻
- 密码二次确认（表单层）；超管 L0 最高，操作目标为超管一律拒绝
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from plugin_host.signals import (
    dept_delete_requested, dept_disabled, dept_updated, user_created,
    user_disable_requested, user_disabled, user_status_changed, user_updated,
)

from .forms import DepartmentForm, RoleForm, UserForm
from .models import Department, Role, User


def require_perm(codename):
    """插件权限装饰器：未登录 → 登录页；无权限码 → 工作台。"""
    def deco(view):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(codename):
                return redirect('index')
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def _clean_multi(post, field):
    """多选字段（M2M）空值清洗：过滤空字符串选项，避免校验报错。"""
    data = post.copy()
    values = [v for v in data.getlist(field) if v]
    if values:
        data.setlist(field, values)
    else:
        data.pop(field, None)
    return data


def _guard_superuser(request, target):
    """权限层级：超管 L0 最高，其他任何用户不能对超管操作。"""
    if target.is_superuser and not request.user.is_superuser:
        return True
    return False


# ---------------------------------------------------------------------------
# 部门
# ---------------------------------------------------------------------------
@require_perm('user_manage')
def department_list(request):
    """部门列表 + 新建 + 修改 + 软删（停用）+ 硬删请求（会签审批）。"""
    if request.method == 'POST':
        action = request.POST.get('action', 'create')
        if action == 'create':
            form = DepartmentForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('user:department_list')
            dept_id = None
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
                form = DepartmentForm()
                return render(request, 'user/department_list.html', {
                    'departments': Department.objects.all().order_by('id'),
                    'form': form,
                    'error': f'部门「{dept.name}」仍有成员，不能直接物理删除；请先调整成员归属。',
                })
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

    departments = Department.objects.all().order_by('id')
    return render(request, 'user/department_list.html', {
        'departments': departments, 'form': form, 'dept_id': dept_id,
        'edit_dept': Department.objects.filter(pk=dept_id).first() if dept_id else None,
    })


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
@require_perm('user_manage')
def user_list(request):
    users = User.objects.select_related('department').prefetch_related('roles').order_by('id')
    return render(request, 'user/user_list.html', {'users': users})


@require_perm('user_manage')
def user_create(request):
    if request.method == 'POST':
        form = UserForm(_clean_multi(request.POST, 'roles'))
        if form.is_valid():
            user = form.save()
            user_created.send(sender=user.__class__, user_id=user.pk)
            return redirect('user:user_list')
    else:
        form = UserForm()
    return render(request, 'user/user_form.html', {'form': form, 'title': _('新建用户')})


@require_perm('user_manage')
def user_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if _guard_superuser(request, user):
        return redirect('user:user_list')
    if request.method == 'POST':
        form = UserForm(_clean_multi(request.POST, 'roles'), instance=user)
        if form.is_valid():
            pwd_changed = bool(form.cleaned_data.get('password'))
            form.save()
            if pwd_changed:
                from plugin_host.signals import password_changed
                password_changed.send(sender=user.__class__, user_id=user.pk,
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
    """用户状态操作：启用 / 禁用 / 冻结权限 / 解冻。

    禁用规则：超管（admin）直接禁用；普通管理员需先冻结权限并发起会签审批，
    全部具备 user_disable_approve 权限的管理员通过后由回调执行禁用。
    """
    target = get_object_or_404(User, pk=user_id)
    if _guard_superuser(request, target):
        return redirect('user:user_list')
    action = request.POST.get('status')
    operator_id = request.user.pk

    if action == 'enable':
        target.is_active = True
        target.permission_frozen = False
        target.save(update_fields=['is_active', 'permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='enabled',
                                 operator_id=operator_id)
    elif action == 'freeze':
        target.permission_frozen = True
        target.save(update_fields=['permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='frozen',
                                 operator_id=operator_id)
    elif action == 'unfreeze':
        target.permission_frozen = False
        target.save(update_fields=['permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='unfrozen',
                                 operator_id=operator_id)
    elif action == 'disable':
        if request.user.is_superuser:
            # admin 直接禁用：冻结权限 + 停用账号
            target.permission_frozen = True
            target.is_active = False
            target.save(update_fields=['permission_frozen', 'is_active', 'updated_at'])
            user_disabled.send(sender=User, user_id=target.pk, operator_id=operator_id)
        else:
            # 普通管理员：先冻结权限（即时生效），再发起禁用会签审批
            target.permission_frozen = True
            target.save(update_fields=['permission_frozen', 'updated_at'])
            user_status_changed.send(sender=User, user_id=target.pk, status='frozen',
                                     operator_id=operator_id)
            user_disable_requested.send(
                sender=User, user_id=target.pk, operator_id=operator_id,
                title=f'用户禁用审批：{target.last_name or target.username}',
                content=f'申请禁用用户「{target.last_name or target.username}」（ID:{target.pk}），'
                        f'需全部审批人通过后执行。')
    return redirect('user:user_list')


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------
@require_perm('user_manage')
def role_list(request):
    roles = Role.objects.prefetch_related('permissions').order_by('id')
    return render(request, 'user/role_list.html', {'roles': roles})


@require_perm('user_manage')
def role_create(request):
    if request.method == 'POST':
        form = RoleForm(_clean_multi(request.POST, 'permissions'))
        if form.is_valid():
            form.save()
            return redirect('user:role_list')
    else:
        form = RoleForm()
    return render(request, 'user/role_form.html', {'form': form, 'title': _('新建角色')})


@require_perm('user_manage')
def role_edit(request, role_id):
    role = get_object_or_404(Role, pk=role_id)
    if request.method == 'POST':
        form = RoleForm(_clean_multi(request.POST, 'permissions'), instance=role)
        if form.is_valid():
            form.save()
            return redirect('user:role_list')
    else:
        form = RoleForm(instance=role)
    return render(request, 'user/role_form.html', {'form': form, 'title': _('编辑角色：%(name)s') % {'name': role.name}})
