"""structure 插件服务：幂等应用职能制架构模板（只创建缺失，不覆盖既有）。"""

from django.apps import apps as dj_apps
from django.contrib.auth.models import Permission
from django.db import transaction

from plugin_host.signals import structure_applied

from .template import (
    ALL_ROLE_PERMISSION_CODES,
    DEFAULT_PASSWORD,
    DEPARTMENTS,
    LEADER_OF,
    MANAGER_ROLES,
    ROLE_PERMISSIONS,
    ROLES,
    USERS,
)


def apply_structure(operator, grant_manager_perms=False):
    """应用模板，返回 (dept_created, role_created, user_created)。

    - 部门：按 name 查，已存在跳过（不覆盖/不恢复软删）
    - 角色：get_or_create；按 ROLE_PERMISSIONS 幂等补齐权限（只增不减）
    - grant_manager_perms=True 时经理类角色额外授予 user_manage（L1，默认不授）
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

    # 2b) 角色权限模板：幂等补齐（只增不减，不覆盖人工调整）
    perm_cache = {
        p.codename: p
        for p in Permission.objects.filter(codename__in=ALL_ROLE_PERMISSION_CODES)
    }
    for rname, codes in ROLE_PERMISSIONS.items():
        role = role_cache.get(rname)
        if role is None:
            continue
        perms = [perm_cache[c] for c in codes if c in perm_cache]
        if perms:
            role.permissions.add(*perms)
    if grant_manager_perms:
        mgr_perm = Permission.objects.filter(codename='user_manage').first()
        if mgr_perm:
            for rname in MANAGER_ROLES:
                role_cache[rname].permissions.add(mgr_perm)

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

    # 3b) 直属上级（v1.5.5）：只补空，不覆盖人工调整
    for account, leader_account in LEADER_OF.items():
        if not leader_account:
            continue
        member = User.objects.filter(username=account).first()
        superior = User.objects.filter(username=leader_account).first()
        if member and superior and member.leader_id is None and member.pk != superior.pk:
            member.leader = superior
            member.save(update_fields=['leader'])

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


def apply_template(operator, payload):
    """应用上传的 XLSX 模板（三工作表已解析）。

    - 部门：按名称查，已存在跳过；新建时父部门必须在本次或既有架构中；
    - 角色：get_or_create，权限只增不减；
    - 用户：按账号查，已存在跳过；新用户用默认密码 + 部门 + 角色；
      既有用户只补空白的直属上级，不改部门/角色/姓名；
    - 整个写入在一个事务里；任何异常都回滚，调用方返回错误而不是半套数据。
    """
    Department = dj_apps.get_model('user', 'Department')
    Role = dj_apps.get_model('user', 'Role')
    User = dj_apps.get_model('user', 'User')

    payload = payload or {}
    departments = payload.get('departments') or []
    roles = payload.get('roles') or []
    users = payload.get('users') or []

    permission_codes = {
        code for role in roles for code in (role.get('permissions') or [])
    }
    permission_map = {
        item.codename: item
        for item in Permission.objects.filter(codename__in=permission_codes)
    }

    dept_created = 0
    role_created = 0
    user_created = 0

    with transaction.atomic():
        dept_cache = {item.name: item for item in Department.objects.all()}
        for item in departments:
            name = item['name']
            if name in dept_cache:
                continue
            parent_name = item.get('parent') or ''
            parent = dept_cache.get(parent_name) if parent_name else None
            if parent_name and parent is None:
                raise ValueError(f'上级部门不存在：{parent_name}')
            dept = Department.objects.create(name=name, parent=parent)
            dept_cache[name] = dept
            dept_created += 1

        role_cache = {item.name: item for item in Role.objects.all()}
        for item in roles:
            name = item['name']
            role = role_cache.get(name)
            if role is None:
                role = Role.objects.create(name=name)
                role_cache[name] = role
                role_created += 1
            perms = [
                permission_map[code] for code in (item.get('permissions') or [])
                if code in permission_map
            ]
            if perms:
                role.permissions.add(*perms)

        account_names = {item['account'] for item in users}
        user_cache = {
            item.username: item
            for item in User.objects.filter(username__in=account_names)
        }
        for item in users:
            account = item['account']
            if account in user_cache:
                continue
            member = User.objects.create_user(username=account, password=DEFAULT_PASSWORD)
            member.last_name = item.get('name') or ''
            member.department = dept_cache.get(item.get('department') or '')
            member.save(update_fields=['last_name', 'department'])
            role = role_cache.get(item.get('role') or '')
            if role is not None:
                member.roles.add(role)
            user_cache[account] = member
            user_created += 1

        # 直属上级：只补空白，不覆盖人工调整；引用对象可以是本次新建的账号。
        for item in users:
            member = user_cache.get(item['account'])
            leader = user_cache.get(item.get('leader') or '')
            if (member and leader and member.pk != leader.pk
                    and member.leader_id is None):
                member.leader = leader
                member.save(update_fields=['leader'])

        from .models import StructureRecord
        StructureRecord.objects.create(
            applied_by=operator,
            dept_created=dept_created,
            role_created=role_created,
            user_created=user_created,
            grant_manager_perms=False)

    structure_applied.send(
        sender=StructureRecord, applied_by_id=operator.pk,
        dept_created=dept_created, role_created=role_created, user_created=user_created)
    return dept_created, role_created, user_created
