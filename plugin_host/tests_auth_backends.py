"""v1.7.7 认证后端插件化：契约校验 + 示例 Provider（用户名或邮箱）。

三个必踩点都在这里钉住：
1. 校验是**纯函数**（`ready()` 只调用它）——否则 `override_settings` 不会重新触发 `ready()`，测不到；
2. `OA_AUTH_BACKENDS=[]` 必须放行（只剩 ModelBackend）；
3. 自定义后端必须自己检查 `is_active`，否则被禁用用户能直接登录。
"""

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from plugin_host.auth_backends.registry import validate_auth_backends
from plugin_host.auth_backends.username_or_email import UsernameOrEmailBackend

User = get_user_model()

LOGIN_URL = '/plugins/auth/login/'
ONLY_MODEL_BACKEND = ['django.contrib.auth.backends.ModelBackend']


class AuthBackendContractTests(TestCase):
    """纯函数校验：非法路径 / 非 BaseBackend 子类 / 未覆盖方法 / 空列表。"""

    def test_valid_backend_passes(self):
        backends = validate_auth_backends(
            ['plugin_host.auth_backends.username_or_email.UsernameOrEmailBackend'])
        self.assertEqual(len(backends), 1)
        self.assertIsInstance(backends[0], UsernameOrEmailBackend)

    def test_empty_list_is_allowed(self):
        """空列表合法：只剩 ModelBackend，不能报错（否则新环境 migrate 就死）。"""
        self.assertEqual(validate_auth_backends([]), [])
        self.assertEqual(validate_auth_backends(None), [])

    def test_missing_path_rejected(self):
        for bad in ('nope.missing.Backend', 'no_dot', 'plugin_host.auth_backends'):
            with self.subTest(path=bad), self.assertRaises(ImproperlyConfigured):
                validate_auth_backends([bad])

    def test_non_backend_class_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_auth_backends(['plugin_host.auth_backends.registry.validate_auth_backends'])

    def test_backend_without_overrides_rejected(self):
        """BaseBackend 本身（authenticate 返回 None、get_user 返回 None）不能当 Provider。"""
        with self.assertRaises(ImproperlyConfigured):
            validate_auth_backends(['django.contrib.auth.backends.BaseBackend'])


@override_settings(AUTHENTICATION_BACKENDS=[
    'plugin_host.auth_backends.username_or_email.UsernameOrEmailBackend',
    'django.contrib.auth.backends.ModelBackend',
])
class UsernameOrEmailLoginTests(TestCase):
    """示例 Provider 的实际登录行为（走 HTTP，验证的是整条链）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'mail_user', email='mail@corp.com', password='MailPass@2026')

    def _post(self, username, password):
        return self.client.post(LOGIN_URL, {'username': username, 'password': password})

    def test_email_login_works(self):
        response = self._post('mail@corp.com', 'MailPass@2026')
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_email_login_is_case_insensitive(self):
        response = self._post('MAIL@CORP.COM', 'MailPass@2026')
        self.assertEqual(response.status_code, 302)

    def test_username_login_still_works(self):
        """同一条链上 username 路径不受影响。"""
        response = self._post('mail_user', 'MailPass@2026')
        self.assertEqual(response.status_code, 302)

    def test_wrong_password_fails(self):
        response = self._post('mail@corp.com', 'wrong')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '用户名或密码错误')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_disabled_user_cannot_login(self):
        """is_active=False 的用户即使密码正确也不能通过自定义后端登录（权限绕过红线）。"""
        User.objects.create_user(
            'disabled_user', email='off@corp.com', password='OffPass@2026', is_active=False)
        self.assertIsNone(authenticate(
            None, username='off@corp.com', password='OffPass@2026'))
        response = self._post('off@corp.com', 'OffPass@2026')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)


@override_settings(AUTHENTICATION_BACKENDS=ONLY_MODEL_BACKEND, OA_AUTH_BACKENDS=[])
class ProviderDisabledTests(TestCase):
    """关掉 Provider 后退回默认 ModelBackend：email 不能登录，username 照常。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'plain_user', email='plain@corp.com', password='PlainPass@2026')

    def test_email_login_fails_without_provider(self):
        response = self.client.post(
            LOGIN_URL, {'username': 'plain@corp.com', 'password': 'PlainPass@2026'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '用户名或密码错误')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_username_login_still_works_without_provider(self):
        response = self.client.post(
            LOGIN_URL, {'username': 'plain_user', 'password': 'PlainPass@2026'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)
