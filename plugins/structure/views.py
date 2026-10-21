"""structure 插件视图：架构总览（只读） + 应用结构（POST，structure_manage）。"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .services import apply_structure
from .template import dept_tree, ROLES, USERS


@login_required
def structure_overview(request):
    """总览：部门树 + 角色清单 + 用户模板分组（按部门）。"""
    users_by_dept = {}
    for account, name, dept, role in USERS:
        users_by_dept.setdefault(dept, []).append({'account': account, 'name': name, 'role': role})
    return render(request, 'structure/overview.html', {
        'dept_tree': dept_tree(),
        'roles': ROLES,
        'users_by_dept': users_by_dept,
        'user_count': len(USERS),
        'last_records': _last_records(),
    })


def _last_records():
    from .models import StructureRecord
    return StructureRecord.objects.select_related('applied_by')[:5]


@login_required
def structure_apply(request):
    """应用模板（POST）。无 structure_manage → 工作台。"""
    if not request.user.has_perm('structure_manage'):
        return redirect('index')
    if request.method == 'POST':
        grant = request.POST.get('grant_manager_perms') == '1'
        counts = apply_structure(request.user, grant_manager_perms=grant)
        return redirect('structure:overview')
    return redirect('structure:overview')
