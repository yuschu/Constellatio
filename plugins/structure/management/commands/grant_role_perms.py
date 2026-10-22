"""management command：为既有角色按结构模板幂等补齐权限（v1.5.4）。

用途：v1.5.3 及更早版本已应用过架构模板、但角色仍是空权限时，
升级后执行一次即可让"对应角色拥有对应权限"；只增不减，可重复执行。
"""

from django.apps import apps as dj_apps
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

from plugins.structure.template import MANAGER_ROLES, ROLE_PERMISSIONS


class Command(BaseCommand):
    help = '按 structure 角色权限模板为既有角色幂等补齐权限（只增不减）'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='只打印将要补齐的权限，不写库')
        parser.add_argument('--revoke-manager-perms', action='store_true',
                            help='同时收回部门经理角色的 L1 user_manage（保留总经理/系统管理员）')

    def handle(self, *args, **options):
        Role = dj_apps.get_model('user', 'Role')
        codes = set().union(*ROLE_PERMISSIONS.values())
        perm_cache = {
            p.codename: p for p in Permission.objects.filter(codename__in=codes)
        }
        dry_run = options['dry_run']
        granted = 0
        role_count = 0
        for name, role_codes in ROLE_PERMISSIONS.items():
            role = Role.objects.filter(name=name).first()
            if role is None:
                continue
            role_count += 1
            existing = set(role.permissions.values_list('codename', flat=True))
            for code in sorted(role_codes - existing):
                perm = perm_cache.get(code)
                if perm is None:
                    continue
                if not dry_run:
                    role.permissions.add(perm)
                granted += 1
                self.stdout.write(f'{role.name}: +{code}')

        revoked = 0
        if options['revoke_manager_perms']:
            user_manage = Permission.objects.filter(codename='user_manage').first()
            for name in sorted(MANAGER_ROLES - {'总经理'}):
                role = Role.objects.filter(name=name).first()
                if role is None or user_manage is None:
                    continue
                if role.permissions.filter(pk=user_manage.pk).exists():
                    if not dry_run:
                        role.permissions.remove(user_manage)
                    revoked += 1
                    self.stdout.write(f'{role.name}: -user_manage (L1 收回，保留 L2 管理岗)')

        prefix = '[dry-run] ' if dry_run else ''
        message = f'{prefix}角色权限补齐：{role_count} 个角色，{granted} 项权限'
        if options['revoke_manager_perms']:
            message += f'；收回 user_manage {revoked} 项'
        self.stdout.write(self.style.SUCCESS(message))
