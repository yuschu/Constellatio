"""auth 插件测试：v1.5 登录页占位入口与密码重置占位页。"""

from django.test import TestCase


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
