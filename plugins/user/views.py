"""user 插件视图：部门 / 用户 / 角色管理（RBAC，权限码 user_manage）。"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from plugin_host.signals import user_created, user_updated

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


# ---------------------------------------------------------------------------
# 部门
# ---------------------------------------------------------------------------
@require_perm('user_manage')
def department_list(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user:department_list')
    else:
        form = DepartmentForm()
    departments = Department.objects.all().order_by('id')
    return render(request, 'user/department_list.html', {'departments': departments, 'form': form})


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
    return render(request, 'user/user_form.html', {'form': form, 'title': '新建用户'})


@require_perm('user_manage')
def user_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = UserForm(_clean_multi(request.POST, 'roles'), instance=user)
        if form.is_valid():
            form.save()
            user_updated.send(sender=user.__class__, user_id=user.pk)
            return redirect('user:user_list')
    else:
        form = UserForm(instance=user)
    return render(request, 'user/user_form.html',
                  {'form': form, 'title': f'编辑用户：{user.last_name or user.username}'})


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
    return render(request, 'user/role_form.html', {'form': form, 'title': '新建角色'})


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
    return render(request, 'user/role_form.html', {'form': form, 'title': f'编辑角色：{role.name}'})
