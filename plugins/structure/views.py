"""structure 插件视图（v1.5.9）。

- `/plugins/structure/`：组织架构页，展示**当前架构**（真实部门 / 角色 / 用户关系树）；
- `/plugins/structure/template/`：**模板架构**详情 + 应用模板表单（应用需 structure_manage）；
- `/plugins/structure/apply/`：POST 应用模板。
"""

from django.apps import apps as dj_apps
from django.db.models import Count
from django.shortcuts import redirect, render

from plugin_host.permissions import require_perm

from .hierarchy import build_department_tree, build_user_tree
from .services import apply_structure
from .template import DEPARTMENTS, ROLE_PERMISSIONS, dept_tree, ROLES, USERS


@require_perm('structure_view')
def structure_overview(request):
    """当前架构：真实部门树 + 真实角色 + 用户关系树 + 责任人清单 + 最近应用。"""
    Role = dj_apps.get_model('user', 'Role')

    dept_tree_data = build_department_tree()
    org_tree = build_user_tree()
    role_rows = [
        {
            'name': role.name,
            'perm_count': role.permission_total,
            'member_count': role.member_total,
        }
        for role in Role.objects.annotate(
            permission_total=Count('permissions', distinct=True),
            member_total=Count('users', distinct=True),
        ).order_by('name')
    ]
    return render(request, 'structure/overview.html', {
        'dept_org': dept_tree_data['roots'],
        'dept_stats': dept_tree_data['stats'],
        'role_rows': role_rows,
        'org_roots': org_tree['roots'],
        'org_rows': org_tree['rows'],
        'org_stats': org_tree['stats'],
        'last_records': _last_records(),
    })


@require_perm('structure_view')
def structure_template(request):
    """模板架构详情：职能制模板部门 / 角色 / 用户；有 structure_manage 才渲染应用表单。"""
    users_by_dept = {}
    for account, name, dept, role in USERS:
        users_by_dept.setdefault(dept, []).append(
            {'account': account, 'name': name, 'role': role})
    role_rows = [
        {'name': name, 'perm_count': len(ROLE_PERMISSIONS.get(name, set())),
         'codes': sorted(ROLE_PERMISSIONS.get(name, set()))}
        for name in ROLES
    ]
    return render(request, 'structure/template.html', {
        'dept_tree': dept_tree(),
        'role_rows': role_rows,
        'dept_count': len(DEPARTMENTS),
        'user_count': len(USERS),
        'users_by_dept': users_by_dept,
        'can_apply': request.user.has_perm('structure_manage'),
        'last_records': _last_records(),
    })


def _last_records():
    from .models import StructureRecord
    return StructureRecord.objects.select_related('applied_by')[:5]


@require_perm('structure_manage')
def structure_apply(request):
    """应用模板（POST）。无 structure_manage → 工作台；成功后回模板详情页。"""
    if request.method == 'POST':
        grant = request.POST.get('grant_manager_perms') == '1'
        apply_structure(request.user, grant_manager_perms=grant)
    return redirect('structure:template')
