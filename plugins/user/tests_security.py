"""安全加固回归（v1.7.1 / P0-11、P1-13、P1-14）。"""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from plugins.user.forms import PasswordForm
from plugins.user.models import User


class SecureDefaultsTests(TestCase):
    """传输安全默认值：本地 / compose 纯 HTTP 部署仍可用。"""

    def test_http_safe_defaults(self):
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_always_on_hardening(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))


class PasswordValidatorTests(TestCase):
    """P1-14：显式设置的新密码必须过 AUTH_PASSWORD_VALIDATORS。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('pwd_user', password='oldpass123')

    def test_profile_password_rejects_weak(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('user:profile_password'), {
            'old_password': 'oldpass123',
            'new_password': '123456',
            'confirm_password': '123456',
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('oldpass123'))

    def test_password_form_accepts_strong(self):
        form = PasswordForm(
            data={'old_password': 'oldpass123',
                  'new_password': 'newpass123',
                  'confirm_password': 'newpass123'},
            user=self.user)
        self.assertTrue(form.is_valid(), form.errors)


class UserEditStatusGuardTests(TestCase):
    """P0-11：编辑用户不能绕过「禁用需会签」。"""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission
        cls.manager = User.objects.create_user('mgr', password='mgrpass')
        cls.manager.user_permissions.add(
            Permission.objects.get(codename='user_manage'))
        cls.admin = User.objects.create_superuser('root', '', 'rootpass')
        cls.target = User.objects.create_user('target', password='oldpass123')

    def _data(self, **extra):
        data = {
            'username': 'target', 'last_name': '目标', 'email': '',
            'department': '', 'leader': '', 'roles': [], 'user_permissions': [],
        }
        data.update(extra)
        return data

    def test_manager_cannot_disable_via_edit(self):
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse('user:user_edit', args=[self.target.pk]), self._data())
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(self.target.permission_frozen)
        self.assertContains(resp, '启用 / 禁用请使用状态操作')

    def test_superuser_can_disable_via_edit(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('user:user_edit', args=[self.target.pk]), self._data())
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(self.target.permission_frozen)

    def test_manager_cannot_enable_via_edit(self):
        """停用 → 启用的切换同样要走状态操作，编辑页一律不生效。"""
        self.target.is_active = False
        self.target.save(update_fields=['is_active'])
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse('user:user_edit', args=[self.target.pk]),
            self._data(is_active='on'))
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertContains(resp, '启用 / 禁用请使用状态操作')

    def test_manager_editing_other_fields_keeps_status(self):
        """不触碰 is_active 的普通编辑仍然放行。"""
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse('user:user_edit', args=[self.target.pk]),
            self._data(is_active='on'))
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
