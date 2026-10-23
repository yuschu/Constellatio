"""structure 插件视图：架构总览（只读，structure_view） + 应用结构（POST，structure_manage）。"""

from django.shortcuts import redirect, render

from plugin_host.permissions import require_perm

from .hierarchy import build_user_tree
from .services import apply_structure
from .template import ROLE_PERMISSIONS, dept_tree, ROLES, USERS


@require_perm('structure_view')
def structure_overview(request):
    """总览：用户关系树（责任划分） + 部门树 + 角色清单 + 用户模板分组。"""
    users_by_dept = {}
    for account, name, dept, role in USERS:
        users_by_dept.setdefault(dept, []).append({'account': account, 'name': name, 'role': role})
    role_rows = [
        {'name': name, 'perm_count': len(ROLE_PERMISSIONS.get(name, set())),
         'codes': sorted(ROLE_PERMISSIONS.get(name, set()))}
        for name in ROLES
    ]
    org_tree = build_user_tree()
    return render(request, 'structure/overview.html', {
        'dept_tree': dept_tree(),
        'role_rows': role_rows,
        'user_count': len(USERS),
        'users_by_dept': users_by_dept,
        'org_roots': org_tree['roots'],
        'org_rows': org_tree['rows'],
        'org_stats': org_tree['stats'],
        'last_records': _last_records(),
    })


def _last_records():
    from .models import StructureRecord
    return StructureRecord.objects.select_related('applied_by')[:5]


@require_perm('structure_manage')
def structure_apply(request):
    """应用模板（POST）。无 structure_manage → 工作台。"""
    if request.method == 'POST':
        grant = request.POST.get('grant_manager_perms') == '1'
        counts = apply_structure(request.user, grant_manager_perms=grant)
        return redirect('structure:overview')
    return redirect('structure:overview')
