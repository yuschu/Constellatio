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

    def test_protected_not_toggleable(self):
        """auth / workspace 禁停：请求后 DB 不产生记录。"""
        for key in ('auth', 'workspace'):
            self._toggle(self.admin, key, False)
            self.assertFalse(PluginSwitch.objects.filter(app_key=key).exists())

    def test_perm_guard(self):
        """无 workspace_manage 权限的用户访问开关页被拒（重定向工作台）。"""
        self.client.force_login(self.admin)
        self.client.post(reverse('workspace:switch_list'))
        noperm = User.objects.create_user('noperm', '', 'nopermpass')
        self.client.force_login(noperm)
        resp = self.client.get(reverse('workspace:switch_list'))
        self.assertEqual(resp.status_code, 302)
