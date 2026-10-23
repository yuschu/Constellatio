"""审批类型 → 管辖部门路由（v1.5.15）。

每类审批交给对应管辖部门的管理用户处理：
- 请假 / 外出 / 加班 / 调休 → 人力资源部（人力资源经理）
- 报销 → 财务部（财务经理）
- 用章 → 行政部（行政经理）

查找顺序：目标部门内持有经理角色 → 目标部门内具备 approval_approve 的启用用户 → None（调用方回退到直属上级 / 超管）。
"""

from django.apps import apps as dj_apps

ROUTING = {
    'leave': {'dept': '人力资源部', 'role': '人力资源经理'},
    'outing': {'dept': '人力资源部', 'role': '人力资源经理'},
    'overtime': {'dept': '人力资源部', 'role': '人力资源经理'},
    'comp': {'dept': '人力资源部', 'role': '人力资源经理'},
    'expense': {'dept': '财务部', 'role': '财务经理'},
    'seal': {'dept': '行政部', 'role': '行政经理'},
}


def routing_target(approval_type):
    """返回该类型对应的 (部门名, 角色名)，未配置返回 None。"""
    rule = ROUTING.get(approval_type)
    if not rule:
        return None
    return rule['dept'], rule['role']


def resolve_approver(approval_type):
    """按审批类型解析默认管辖部门审批人；部门 / 插件缺失时返回 None 由调用方回退。"""
    candidates = candidate_approvers(approval_type)
    return candidates[0] if candidates else None


def candidate_approvers(approval_type):
    """审批人可选范围（v1.5.18）：管辖部门内该经理角色 → 部门内具备 approval_approve 的启用用户。"""
    rule = ROUTING.get(approval_type)
    if not rule:
        return []
    try:
        Department = dj_apps.get_model('user', 'Department')
        User = dj_apps.get_model('user', 'User')
    except LookupError:
        return []
    department = Department.objects.filter(name=rule['dept'], is_active=True).first()
    if department is None:
        return []
    managers = list(User.objects.filter(
        is_active=True, department=department, roles__name=rule['role'],
        permission_frozen=False).order_by('pk'))
    if managers:
        return managers
    return [
        user for user in User.objects.filter(is_active=True, department=department).order_by('pk')
        if user.has_perm('approval_approve')
    ]
