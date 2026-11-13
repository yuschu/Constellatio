"""workspace 插件测试：DB 开关覆盖静态配置、禁停清单、权限守卫。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from plugin_host.registry import get_enabled_plugins

from .models import PluginSwitch

User = get_user_model()


class PluginSwitchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin', '', 'adminpass')
        cls.manager = User.objects.create_user('mgr', '', 'mgrpass')
        cls.manager.roles.create(name='MGRROLE')

    def _toggle(self, user, key, enabled):
        self.client.force_login(user)
        return self.client.post(reverse('workspace:switch_toggle', args=[key]),
                                {'enabled': '1' if enabled else '0'})

    def test_db_switch_overrides_static(self):
        """DB 开关优先：停用 notice 后 get_enabled_plugins 不含 notice。"""
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        keys = [k for k, _ in get_enabled_plugins()]
        self.assertNotIn('notice', keys)
        self.assertIn('auth', keys)

    def test_toggle_rejects_get(self):
        """开关切换只接受 POST：GET 不写库。"""
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse('workspace:switch_toggle', args=['notice']))
        self.assertEqual(resp.status_code, 405)
        self.assertFalse(PluginSwitch.objects.filter(app_key='notice').exists())

    def test_direct_orm_switch_takes_effect_immediately(self):
        """直接 ORM 创建 / 删除开关也立即生效（save/delete 失效缓存）。"""
        switch = PluginSwitch.objects.create(app_key='notice', enabled=False)
        self.assertNotIn('notice', [k for k, _ in get_enabled_plugins()])
        switch.delete()
        self.assertIn('notice', [k for k, _ in get_enabled_plugins()])

    def test_toggle_persists_and_sends_signal(self):
        """toggle 写 DB 且触发 plugin_toggled 信号。"""
        received = []
        from plugin_host.signals import plugin_toggled
        plugin_toggled.connect(lambda sender, **kw: received.append(kw), weak=False)
        self._toggle(self.admin, 'notice', False)
        self.assertEqual(PluginSwitch.objects.get(app_key='notice').enabled, False)
        self.assertEqual(received[-1]['app_key'], 'notice')

    def test_only_workspace_is_protected(self):
        """v2.2.0：禁停清单只剩 workspace；系统底座改用 builtin，界面既不可见也不可停。"""
        from .views import PROTECTED
        self.assertEqual(PROTECTED, {'workspace'})
        self._toggle(self.admin, 'workspace', False)
        self.assertFalse(PluginSwitch.objects.filter(app_key='workspace').exists())

    def test_builtin_plugins_hidden_from_list_and_toggle(self):
        """v2.2.0：内置插件（语言 / 认证 / 账号 / 组织架构 / 插件页 / 图表）不外显。

        v2.2.1 加 core：容器自己的菜单来源（看板入口），同样是内置底座。
        UI 上既看不到卡片，POST 开关也不落库；命令行 `plugin_switch` 仍是兜底出口。
        """

        from plugin_host.registry import PLUGIN_REGISTRY

        from .views import switch_list_context

        builtin = {key for key, meta in PLUGIN_REGISTRY.items() if meta.builtin}
        self.assertEqual(
            builtin,
            {'auth', 'user', 'structure', 'workspace', 'language', 'charts', 'core'})

        rows = {row['key'] for row in switch_list_context()['rows']}
        self.assertFalse(rows & builtin)
        self.assertEqual(
            rows, {'approval', 'notice', 'attendance', 'blockchain',
                   'assistant', 'notify', 'sso'})

        for key in sorted(builtin - {'workspace'}):
            PluginSwitch.objects.filter(app_key=key).delete()
            self._toggle(self.admin, key, False)
            self.assertFalse(PluginSwitch.objects.filter(app_key=key).exists())

    def test_disable_auth_closes_login_but_keeps_session(self):
        """停用 auth（命令行 / 直接写库）：登录页 404，已登录会话的工作台仍可用。"""
        PluginSwitch.objects.create(app_key='auth', enabled=False)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/plugins/auth/login/').status_code, 404)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_switch_ui_uses_toggle_switch(self):
        """开关 UI：业务插件是 checkbox 开关；内置插件整行都不出现。"""
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, 'role="switch"')
        self.assertContains(resp, 'data-plugin-switch')
        self.assertContains(resp, reverse('workspace:switch_toggle', args=['notice']))
        # v2.2.0：没有「系统必需」这种占位卡片了
        self.assertNotContains(resp, '系统必需')

    def test_switch_list_hides_builtin_plugins(self):
        """内置插件不再出现在清单里，也不再提示「停用后果 / 命令行恢复」。"""
        self.client.force_login(self.admin)
        self.client.cookies['django_language'] = 'zh-hans'
        resp = self.client.get(reverse('workspace:switch_list'))
        for key in ('auth', 'user', 'structure', 'language', 'workspace', 'charts'):
            self.assertNotContains(resp, f'data-plugin-key="{key}"')
        self.assertNotContains(resp, 'plugin_switch on auth')
        self.assertContains(resp, '业务插件的运行时启停')

    def test_cli_switch_roundtrip(self):
        """兜底命令：off auth 写库，on auth 恢复（不依赖 HTTP）。"""
        import io

        from django.core.management import call_command
        out = io.StringIO()
        call_command('plugin_switch', 'off', 'auth', stdout=out)
        self.assertFalse(PluginSwitch.objects.get(app_key='auth').enabled)
        self.assertNotIn('auth', [name for name, _ in get_enabled_plugins()])
        call_command('plugin_switch', 'on', 'auth', stdout=io.StringIO())
        self.assertTrue(PluginSwitch.objects.get(app_key='auth').enabled)
        self.assertIn('auth', [name for name, _ in get_enabled_plugins()])
        listing = io.StringIO()
        call_command('plugin_switch', 'list', stdout=listing)
        self.assertIn('auth', listing.getvalue())

    def test_home_entries_follow_plugin_switches(self):
        """v1.5.7：工作台入口随插件停用收敛（公告 / 审批 / 考勤卡与快捷发起）。"""
        self._toggle(self.admin, 'notice', False)
        self._toggle(self.admin, 'approval', False)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '/plugins/notice/')
        self.assertNotContains(resp, '/plugins/approval/')
        self._toggle(self.admin, 'notice', True)
        resp = self.client.get('/')
        self.assertContains(resp, '/plugins/notice/')

    def test_perm_guard(self):
        """无 workspace_manage 权限的用户访问开关页被拒（重定向工作台）。"""
        self.client.force_login(self.admin)
        self.client.post(reverse('workspace:switch_list'))
        noperm = User.objects.create_user('noperm', '', 'nopermpass')
        self.client.force_login(noperm)
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertEqual(resp.status_code, 403)              # v1.7.9：无权 → 403
        self.assertContains(resp, '403', status_code=403)

    def test_switch_list_localized_plugin_titles(self):
        """插件名称随语言切换：清单只剩业务插件，内置插件两种语言都不出现。"""
        self.client.force_login(self.admin)
        self.client.cookies['django_language'] = 'zh-hans'
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, '审批中心')
        self.assertContains(resp, '公告通知')
        self.assertNotContains(resp, '用户与组织')
        self.client.cookies['django_language'] = 'en'
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, 'Approval')
        self.assertContains(resp, 'Notices')
        self.assertNotContains(resp, 'Users &amp; organization')
        self.assertNotContains(resp, '认证')


class ChartPluginSwitchTests(TestCase):
    """v1.6.1 / v2.2.0：图表引擎是内置 Provider 插件——清单不外显，命令行仍可停。"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('chartadmin', '', 'chartpass')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_switch_list_hides_chart_engine(self):
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertNotContains(resp, '图表引擎')
        self.assertNotContains(resp, reverse('workspace:switch_toggle', args=['charts']))

    def test_toggle_chart_disables_and_restores_provider(self):
        from plugin_host.charts import get_active_chart

        PluginSwitch.objects.create(app_key='charts', enabled=False)
        self.assertIsNone(get_active_chart())

        PluginSwitch.objects.filter(app_key='charts').delete()
        self.assertIsNotNone(get_active_chart())

    def test_cli_lists_and_toggles_chart_provider(self):
        import io

        from django.core.management import call_command

        listing = io.StringIO()
        call_command('plugin_switch', 'list', stdout=listing)
        self.assertIn('charts', listing.getvalue())

        call_command('plugin_switch', 'off', 'charts', stdout=io.StringIO())
        self.assertFalse(PluginSwitch.objects.get(app_key='charts').enabled)
        listing = io.StringIO()
        call_command('plugin_switch', 'list', stdout=listing)
        self.assertIn('off  charts', listing.getvalue())

        call_command('plugin_switch', 'on', 'charts', stdout=io.StringIO())
        self.assertTrue(PluginSwitch.objects.get(app_key='charts').enabled)

