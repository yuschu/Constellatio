"""user 插件权限等级注册表（v1.5.4）。

等级（数字越小权限越高）：
- L0 超级管理员：is_superuser，直接放行全部权限码
- L1 系统管理：组织/用户、插件开关、结构模板应用、留痕校验
- L2 管理岗：审批与会签、签到详情、公告发布、留痕/架构只读
- L3 员工：审批发起等普通操作

全员基线权限（BASELINE_PERMS）：
- attendance_view / attendance_check / notice_view
  任何已登录且未冻结权限的账号天然拥有，无需分配角色。
"""

from django.db.models import Case, IntegerField, Value, When
from django.utils.translation import gettext_lazy as _

LEVEL_ROOT = 0
LEVEL_SYSTEM = 10
LEVEL_MANAGER = 20
LEVEL_STAFF = 30

LEVEL_LABELS = {
    LEVEL_ROOT: _('L0 超级管理员'),
    LEVEL_SYSTEM: _('L1 系统管理'),
    LEVEL_MANAGER: _('L2 管理岗'),
    LEVEL_STAFF: _('L3 员工'),
}

# 权限码 → 等级；未登记的权限码按 L3 处理（向前兼容新增插件权限）
PERMISSION_LEVELS = {
    'user_manage': LEVEL_SYSTEM,
    'workspace_manage': LEVEL_SYSTEM,
    'structure_manage': LEVEL_SYSTEM,
    'blockchain_verify': LEVEL_SYSTEM,
    'dept_delete_approve': LEVEL_MANAGER,
    'user_disable_approve': LEVEL_MANAGER,
    'approval_approve': LEVEL_MANAGER,
    'attendance_report_view': LEVEL_MANAGER,
    'notice_manage': LEVEL_MANAGER,
    'structure_view': LEVEL_MANAGER,
    'blockchain_view': LEVEL_MANAGER,
    'approval_view': LEVEL_STAFF,
    'attendance_view': LEVEL_STAFF,
    'attendance_check': LEVEL_STAFF,
    'notice_view': LEVEL_STAFF,
    'auth_login': LEVEL_STAFF,
}

# 全员基线权限：登录即用，冻结权限时同样失效
BASELINE_PERMS = frozenset({'attendance_view', 'attendance_check', 'notice_view'})


def bare_codename(perm):
    """'app.codename' → 'codename'；裸码原样返回。"""
    return (perm or '').rsplit('.', 1)[-1]


def is_baseline_perm(perm):
    return bare_codename(perm) in BASELINE_PERMS


def permission_level(codename):
    """权限码等级；未登记按 L3。"""
    return PERMISSION_LEVELS.get(bare_codename(codename), LEVEL_STAFF)


def permission_level_label(codename):
    return LEVEL_LABELS[permission_level(codename)]


def role_level(role):
    """角色等级 = 角色权限中的最高等级；空权限角色按 L3。"""
    levels = [permission_level(p.codename) for p in role.permissions.all()]
    return min(levels) if levels else LEVEL_STAFF


def user_level(user):
    """用户等级：超管 L0；其余取基线 L3 与自身权限中的最高等级。"""
    if getattr(user, 'is_superuser', False):
        return LEVEL_ROOT
    levels = [LEVEL_STAFF]
    if getattr(user, 'pk', None):
        levels.extend(permission_level(p.codename)
                      for p in user.user_permissions.all())
        for role in user.roles.all():
            levels.append(role_level(role))
    return min(levels)


def level_ordering_case():
    """按等级排序的 Case：L1 → L2 → L3（未登记默认 L3）。"""
    whens = []
    for level in (LEVEL_SYSTEM, LEVEL_MANAGER, LEVEL_STAFF):
        codes = [code for code, lvl in PERMISSION_LEVELS.items() if lvl == level]
        if codes:
            whens.append(When(codename__in=codes, then=Value(level)))
    return Case(*whens, default=Value(LEVEL_STAFF), output_field=IntegerField())


def ordered_permissions(queryset):
    """权限查询集按等级、app、codename 排序（用于角色/用户表单）。"""
    return queryset.annotate(_perm_level=level_ordering_case()).order_by(
        '_perm_level', 'content_type__app_label', 'codename')
