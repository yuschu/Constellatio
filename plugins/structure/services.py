"""structure 插件服务：幂等应用职能制架构模板（只创建缺失，不覆盖既有）。"""

from django.apps import apps as dj_apps
from django.contrib.auth.models import Permission

from plugin_host.signals import structure_applied

from .template import DEFAULT_PASSWORD, DEPARTMENTS, MANAGER_ROLES, ROLES, USERS


def apply_structure(operator, grant_manager_perms=False):
    """应用模板，返回 (dept_created, role_created, user_created)。

    - 部门：按 name 查，已存在跳过（不覆盖/不恢复软删）
    - 角色：get_or_create；grant_manager_perms=True 时经理类角色加 user_manage
    - 用户：按 username 查，已存在跳过；新用户设默认密码 + 部门 + 角色
    """
    Department = dj_apps.get_model('user', 'Department')
    Role = dj_apps.get_model('user', 'Role')
    User = dj_apps.get_model('user', 'User')

    # 1) 部门（先一级后二级）
    dept_created = 0
    dept_cache = {}
    for name, parent in DEPARTMENTS:
        if Department.objects.filter(name=name).exists():
            dept_cache[name] = Department.objects.get(name=name)
            continue
        dept = Department.objects.create(
            name=name, parent=dept_cache.get(parent) if parent else None)
        dept_cache[name] = dept
        dept_created += 1

    # 2) 角色
    role_created = 0
    role_cache = {}
    for rname in ROLES:
        role, created = Role.objects.get_or_create(name=rname)
        role_cache[rname] = role
        if created:
            role_created += 1
    if grant_manager_perms:
        perm = Permission.objects.get(codename='user_manage')
        for rname in MANAGER_ROLES:
            role = role_cache[rname]
            if not role.permissions.filter(pk=perm.pk).exists():
                role.permissions.add(perm)

    # 3) 用户模板
    user_created = 0
    for account, name, dept, role_name in USERS:
        if User.objects.filter(username=account).exists():
            continue
        user = User.objects.create_user(username=account, password=DEFAULT_PASSWORD)
        user.last_name = name
        user.department = dept_cache.get(dept)
        user.save(update_fields=['last_name', 'department'])
        if role_name in role_cache:
            user.roles.add(role_cache[role_name])
        user_created += 1

    # 4) 留痕记录 + 上链信号
    from .models import StructureRecord
    StructureRecord.objects.create(
        applied_by=operator,
        dept_created=dept_created,
        role_created=role_created,
        user_created=user_created,
        grant_manager_perms=grant_manager_perms)
    structure_applied.send(
        sender=StructureRecord, applied_by_id=operator.pk,
        dept_created=dept_created, role_created=role_created, user_created=user_created)

    return dept_created, role_created, user_created
