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

    def test_toggle_persists_and_sends_signal(self):
        """toggle 写 DB 且触发 plugin_toggled 信号。"""
        received = []
        from plugin_host.signals import plugin_toggled
        plugin_toggled.connect(lambda sender, **kw: received.append(kw), weak=False)
        self._toggle(self.admin, 'notice', False)
        self.assertEqual(PluginSwitch.objects.get(app_key='notice').enabled, False)
        self.assertEqual(received[-1]['app_key'], 'notice')

    def test_only_workspace_is_protected(self):
        """v1.5.7：禁停清单只剩 workspace；auth / user / structure / language 可停用。"""
        from .views import PROTECTED
        self.assertEqual(PROTECTED, {'workspace'})
        self._toggle(self.admin, 'workspace', False)
        self.assertFalse(PluginSwitch.objects.filter(app_key='workspace').exists())
        for key in ('auth', 'user', 'structure', 'language'):
            PluginSwitch.objects.filter(app_key=key).delete()
            self._toggle(self.admin, key, False)
            self.assertFalse(PluginSwitch.objects.get(app_key=key).enabled)
            self.assertNotIn(key, [name for name, _ in get_enabled_plugins()])

    def test_disable_auth_closes_login_but_keeps_session(self):
        """停用 auth：登录页 404，已登录会话的工作台仍可用。"""
        self._toggle(self.admin, 'auth', False)
        self.assertEqual(self.client.get('/plugins/auth/login/').status_code, 404)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_switch_ui_uses_toggle_switch(self):
        """v1.5.7：停用/启用按钮改为开关；受保护插件为禁用开关 + 系统必需。"""
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, 'role="switch"')
        self.assertContains(resp, 'data-plugin-switch')
        self.assertContains(resp, '系统必需')
        self.assertContains(resp, reverse('workspace:switch_toggle', args=['notice']))

    def test_switch_list_warns_on_critical_plugins(self):
        """风险提示：auth 行显示停用后果与命令行恢复方式。"""
        self.client.force_login(self.admin)
        self.client.cookies['django_language'] = 'zh-hans'
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, '登录 / 登出入口关闭')
        self.assertContains(resp, 'plugin_switch on auth')

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
        self.assertEqual(resp.status_code, 302)

    def test_switch_list_localized_plugin_titles(self):
        """插件名称随语言切换：中文显示中文名，英文显示英文名。"""
        self.client.force_login(self.admin)
        self.client.cookies['django_language'] = 'zh-hans'
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, '认证')
        self.assertContains(resp, '用户与组织')
        self.assertContains(resp, '插件')
        self.client.cookies['django_language'] = 'en'
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertContains(resp, 'Authentication')
        self.assertContains(resp, 'Users &amp; organization')
        self.assertContains(resp, 'Plugins')
        self.assertNotContains(resp, '用户与组织')
