"""structure 插件视图（v1.5.12）。

- `/plugins/structure/`：组织架构页，展示**当前架构**（真实部门 / 角色 / 用户关系树）；
- `/plugins/structure/template/`：**模板架构**详情 + 应用模板表单（应用需 structure_manage）；
- `/plugins/structure/apply/`：POST 应用模板；
- `/plugins/structure/user/<id>/`：角色成员 → 用户资料（只读）。
"""

from django.apps import apps as dj_apps
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from plugin_host.permissions import require_perm

from .hierarchy import build_department_tree, build_user_tree
from .services import apply_structure
from .template import DEPARTMENTS, ROLE_PERMISSIONS, ROLES, USERS, dept_tree


@require_perm('structure_view')
def structure_overview(request):
    """当前架构：真实部门树 + 真实角色 + 用户关系树 + 责任人清单 + 最近应用。"""
    return render(request, 'structure/overview.html', _overview_context(request))


def _overview_context(request):
    """组织架构页的上下文（v2.1.3 抽出）：概览与「用户资料」弹层共用一份。"""
    Role = dj_apps.get_model('user', 'Role')

    dept_tree_data = build_department_tree()
    org_tree = build_user_tree()
    # v1.5.10：角色卡片携带成员明细，供前端弹窗展示（prefetch 避免 N+1）
    role_rows = []
    for role in Role.objects.prefetch_related(
            'permissions', 'users__department').order_by('name'):
        members = [
            {
                'name': user.last_name or user.username,
                'account': user.username,
                'dept': user.department.name if user.department_id else '',
                'is_active': user.is_active,
                'url': reverse('structure:user_detail', args=[user.pk]),
            }
            for user in role.users.all()
        ]
        role_rows.append({
            'name': role.name,
            'perm_count': len(role.permissions.all()),
            'member_count': len(members),
            'members': members,
        })
    ctx = {
        'dept_org': dept_tree_data['roots'],
        'dept_stats': dept_tree_data['stats'],
        'role_rows': role_rows,
        'org_roots': org_tree['roots'],
        'org_rows': org_tree['rows'],
        'org_stats': org_tree['stats'],
        'last_records': _last_records(),
    }
    # v2.1.3：模板架构改设置弹层（`?view=template`）；模板页要 structure_view，
    # 无权限的账号既不渲染入口也不渲染弹层（避免越权取数）。
    if request.user.has_perm('structure_view'):
        overview_url = reverse('structure:overview')
        template_ctx = _template_context(request)
        # 键名与组织架构页的 role_rows 冲突，所以加 tmpl_ 前缀，弹层 include 里再映射回去
        ctx.update({
            'tmpl_dept_tree': template_ctx['dept_tree'],
            'tmpl_role_rows': template_ctx['role_rows'],
            'tmpl_dept_count': template_ctx['dept_count'],
            'tmpl_user_count': template_ctx['user_count'],
            'tmpl_users_by_dept': template_ctx['users_by_dept'],
            'tmpl_can_apply': template_ctx['can_apply'],
            'tmpl_last_records': template_ctx['last_records'],
        })
        ctx.update({
            'template_open': request.method == 'GET' and request.GET.get('view') == 'template',
            'template_url': f'{overview_url}?view=template',
            'overview_url': overview_url,
        })
    return ctx


def _template_context(request):
    """模板架构上下文（组织架构页弹层与独立深链页同一口径）。"""
    users_by_dept = {}
    for account, name, dept, role in USERS:
        users_by_dept.setdefault(dept, []).append(
            {'account': account, 'name': name, 'role': role})
    role_rows = [
        {'name': name, 'perm_count': len(ROLE_PERMISSIONS.get(name, set())),
         'codes': sorted(ROLE_PERMISSIONS.get(name, set()))}
        for name in ROLES
    ]
    return {
        'dept_tree': dept_tree(),
        'role_rows': role_rows,
        'dept_count': len(DEPARTMENTS),
        'user_count': len(USERS),
        'users_by_dept': users_by_dept,
        'can_apply': request.user.has_perm('structure_manage'),
        'last_records': _last_records(),
    }


@require_perm('structure_view')
def structure_template(request):
    """模板架构详情：职能制模板部门 / 角色 / 用户；有 structure_manage 才渲染应用表单。

    v2.1.3：独立深链 /structure/template/ 是设置面板的无遮罩版本；组织架构页的
    「查看模板 →」用 `?view=template` 打开同一块面板的弹层。
    """
    ctx = _template_context(request)
    ctx['back_url'] = reverse('structure:overview')
    return render(request, 'structure/template.html', ctx)


def _last_records():
    from .models import StructureRecord
    return StructureRecord.objects.select_related('applied_by')[:5]


@require_perm('structure_view')
def structure_user_detail(request, user_id):
    """角色成员 → 用户资料（只读，v1.5.12）。

    与组织关系树同权限口径（structure_view 可看全员，不做行级隔离）。

    v2.1.3：不再是另一套整页 —— 渲染的是组织架构页本身，资料放进叠在它上面的
    设置弹层（服务端直接渲染成打开态）。地址仍为 /structure/user/<id>/，
    所以侧栏、面包屑、返回都不用另写一套。
    """
    User = dj_apps.get_model('user', 'User')
    target = get_object_or_404(
        User.objects.select_related('department', 'leader').prefetch_related('roles'),
        pk=user_id)
    ctx = _overview_context(request)
    ctx.update({
        'target': target,
        'is_self': target.pk == request.user.pk,
        'can_manage': request.user.has_perm('user_manage'),
        'user_detail_open': True,
    })
    return render(request, 'structure/overview.html', ctx)


@require_perm('structure_manage')
def structure_apply(request):
    """应用模板（POST）。无 structure_manage → 工作台；成功后回模板详情页。"""
    if request.method == 'POST':
        grant = request.POST.get('grant_manager_perms') == '1'
        apply_structure(request.user, grant_manager_perms=grant)
    return redirect('structure:template')
