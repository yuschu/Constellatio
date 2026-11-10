"""auth 插件测试：v1.5 登录页占位入口与密码重置占位页；v1.7.4 收尾登录回跳安全。"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class AuthPlaceholderTest(TestCase):
    def test_login_has_sso_entry(self):
        """v1.7.0：企业 SSO 插件启用时，登录页提供可用入口（不再是禁用占位）。"""
        response = self.client.get('/plugins/auth/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SSO')
        self.assertContains(response, '忘记密码')
        self.assertContains(response, '/plugins/sso/')
        self.assertNotContains(response, 'aria-disabled="true"')

    def test_login_error_preserves_username(self):
        response = self.client.post('/plugins/auth/login/', {
            'username': 'alice', 'password': 'bad'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="alice"')

    def test_password_reset_notice(self):
        response = self.client.get('/plugins/auth/password-reset/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '暂未开放')
        self.assertContains(response, '请联系管理员重置密码')


class LoginNextRedirectSecurityTests(TestCase):
    """v1.7.4 收尾：登录后回跳只允许同站地址（防开放重定向）。"""

    @classmethod
    def setUpTestData(cls):
        User.objects.create_user('next_user', password='NextUser@2026')

    def _login_with_next(self, next_value):
        return self.client.post('/plugins/auth/login/', {
            'username': 'next_user',
            'password': 'NextUser@2026',
            'next': next_value,
        })

    def test_external_next_rejected(self):
        """外站地址不跳，回工作台，且 Location 不出现外站域名。"""
        response = self._login_with_next('https://evil.example.com/steal')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')
        self.assertNotIn('evil.example.com', response.headers['Location'])

    def test_protocol_relative_next_rejected(self):
        """协议相对 URL（//evil.com）是最常见的绕过形式，同样不跳。"""
        response = self._login_with_next('//evil.example.com/steal')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')
        self.assertNotIn('evil.example.com', response.headers['Location'])
