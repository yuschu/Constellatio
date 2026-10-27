"""plugin_host.registry / discover 单元测试：系统检查、权限集合、开关缓存。

重点覆盖 v1.7.x 改造：
- 权限码冲突由 Django 系统检查返回 Error，不再 ready() 直接 raise；
- get_menus 用一次性权限集合替代逐菜单 has_perm（语义必须等价）；
- PluginSwitch 直写 ORM / 删除后开关立即可见，TTL 缓存可失效。
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.checks import Error
from django.db import connection
from django.db.utils import OperationalError
from django.test import SimpleTestCase, TestCase

from plugin_host.discover import assert_registry_ok, check_registry
from plugin_host.registry import (
    PLUGIN_REGISTRY,
    PluginMeta,
    get_enabled_plugins,
    get_menus,
    get_plugin_switches,
    invalidate_plugin_switch_cache,
    plugin_counts,
    plugin_enabled,
)
from plugins.user.models import Role

User = get_user_model()
P = Permission.objects


class RegistryCheckTests(SimpleTestCase):
    """discover.check_registry：注册为 Django 系统检查，冲突返回 Error。"""

    def test_assert_registry_ok_passes(self):
        self.assertEqual(check_registry(), [])
        assert_registry_ok()

    def test_duplicate_permission_returns_error(self):
        duplicate = PluginMeta(
            name='__temp_dup_plugin__', version='0.0.0',
            permissions=['workspace_manage'])
        PLUGIN_REGISTRY[duplicate.name] = duplicate
        self.addCleanup(PLUGIN_REGISTRY.pop, duplicate.name, None)

        errors = check_registry()
        self.assertTrue(errors)
        self.assertTrue(all(isinstance(item, Error) for item in errors))
        self.assertEqual(errors[0].id, 'plugin_host.E001')
        self.assertIn('workspace_manage', errors[0].msg)

    def test_assert_registry_ok_raises_on_conflict(self):
        duplicate = PluginMeta(
            name='__temp_dup_plugin2__', version='0.0.0',
            permissions=['workspace_manage'])
        PLUGIN_REGISTRY[duplicate.name] = duplicate
        self.addCleanup(PLUGIN_REGISTRY.pop, duplicate.name, None)
        with self.assertRaises(ValueError):
            assert_registry_ok()


def _expected_menus(user):
    """逐菜单 has_perm 的参考实现（旧语义）。"""
    menus = []
    for name, meta in get_enabled_plugins():
        for menu in meta.menus:
            perm = menu.get('perm')
            if perm and not user.has_perm(perm):
                continue
            menus.append({**menu, 'plugin': name})
    return menus


class MenuPermissionTests(TestCase):
    """get_menus 的权限集合判定必须与 User.has_perm 逐条判定等价。"""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('regstaff', '', 'pw')
        cls.manager = User.objects.create_user('regmgr', '', 'pw')
        role = Role.objects.create(name='REG_MANAGER')
        for code in ('structure_view', 'workspace_manage', 'approval_view'):
            role.permissions.add(P.get(codename=code))
        cls.manager.roles.add(role)
        cls.frozen = User.objects.create_user(
            'regfrozen', '', 'pw', permission_frozen=True)
        cls.inactive = User.objects.create_user(
            'reginactive', '', 'pw', is_active=False)
        cls.admin = User.objects.create_superuser('regroot', '', 'pw')

    def _assert_equivalent(self, user):
        self.assertEqual(get_menus(user), _expected_menus(user))

    def test_anonymous(self):
        self._assert_equivalent(AnonymousUser())

    def test_baseline_user(self):
        self._assert_equivalent(self.staff)

    def test_role_user(self):
        self._assert_equivalent(self.manager)

    def test_personal_permission(self):
        self.staff.user_permissions.add(P.get(codename='workspace_manage'))
        self._assert_equivalent(self.staff)

    def test_superuser(self):
        self._assert_equivalent(self.admin)

    def test_frozen_user(self):
        self._assert_equivalent(self.frozen)

    def test_inactive_user(self):
        self._assert_equivalent(self.inactive)

    def test_app_dotted_perm_matches_bare_codename(self):
        """has_perm 支持 'app.codename'，菜单判定需同样归一化。"""
        self.assertTrue(self.manager.has_perm('user.structure_view'))
        menu = {'label': 'x', 'icon': 'x', 'url': '/x/',
                'perm': 'user.structure_view'}
        meta = PluginMeta(name='__temp_menu_plugin__', version='0.0.0',
                          menus=[menu])
        PLUGIN_REGISTRY[meta.name] = meta
        self.addCleanup(PLUGIN_REGISTRY.pop, meta.name, None)
        # 只关心附加菜单是否出现；用用户直接构造（不经 OA_PLUGINS）。
        menus = get_menus(self.manager, [('__temp_menu_plugin__', meta)])
        self.assertEqual(len(menus), 1)
        menus = get_menus(self.staff, [('__temp_menu_plugin__', meta)])
        self.assertEqual(menus, [])


class PluginCountTests(TestCase):
    """plugin_enabled / plugin_counts 统一口径：静态 → DB → 默认启用。"""

    def setUp(self):
        invalidate_plugin_switch_cache()

    def test_defaults_enabled(self):
        self.assertTrue(plugin_enabled('charts'))
        self.assertTrue(plugin_enabled('notice'))

    def test_provider_switch_overrides_default(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='charts', enabled=False)
        self.assertFalse(plugin_enabled('charts'))

    def test_counts_cover_registry_including_provider(self):
        enabled, total = plugin_counts()
        self.assertEqual(total, len(PLUGIN_REGISTRY))
        self.assertIn('charts', PLUGIN_REGISTRY)
        self.assertEqual(
            enabled,
            sum(1 for key in PLUGIN_REGISTRY if plugin_enabled(key)))

        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        new_enabled, new_total = plugin_counts()
        self.assertEqual(new_total, total)
        self.assertEqual(new_enabled, enabled - 1)


class PluginSwitchCacheTests(TestCase):
    """直接 ORM 造 / 删 PluginSwitch 必须立即生效，不能只靠信号。"""

    def setUp(self):
        invalidate_plugin_switch_cache()

    def test_create_takes_effect_immediately(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        self.assertFalse(plugin_enabled('notice'))
        self.assertNotIn('notice', [key for key, _ in get_enabled_plugins()])

    def test_instance_delete_takes_effect_immediately(self):
        from plugins.workspace.models import PluginSwitch
        switch = PluginSwitch.objects.create(app_key='notice', enabled=False)
        switch.delete()
        self.assertTrue(plugin_enabled('notice'))
        self.assertIn('notice', [key for key, _ in get_enabled_plugins()])

    def test_queryset_delete_takes_effect_immediately(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        PluginSwitch.objects.filter(app_key='notice').delete()
        self.assertTrue(plugin_enabled('notice'))

    def test_ttl_cache_reuses_snapshot_until_invalidated(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        with mock.patch.object(connection, 'in_atomic_block', False):
            self.assertFalse(get_plugin_switches()['notice'])
            with self.assertNumQueries(0):
                get_plugin_switches()
            # QuerySet.update 不经过 save()/信号：缓存期内仍是旧快照
            PluginSwitch.objects.filter(app_key='notice').update(enabled=True)
            self.assertFalse(get_plugin_switches()['notice'])
            invalidate_plugin_switch_cache()
            self.assertTrue(get_plugin_switches()['notice'])

    def test_switch_table_error_degrades_to_static(self):
        with mock.patch(
                'plugins.workspace.models.PluginSwitch.objects.values_list',
                side_effect=OperationalError('table missing')):
            self.assertEqual(get_plugin_switches(), {})
            self.assertTrue(plugin_enabled('notice'))
