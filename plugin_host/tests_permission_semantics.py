"""v1.7.9 越权反馈语义：已登录无权 → 403；未登录仍 302 到登录页。

分工：
- `require_perm` 只管 raise `ObjectPermissionDenied`，HTML/JSON 由 `ExceptionGuardMiddleware` 决定；
- 403 页面固定文案、**不回显异常 message**（v1.7.5 边界，本版不改）；
- JSON 错误体带我们抛的 message（本版修的 `_error_response` 硬编码问题）。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from plugins.user.models import Role

User = get_user_model()

PROTECTED = '/plugins/structure/'
STATS_PATH = '/plugins/blockchain/stats/'


class PermissionSemanticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('sem_staff', password='pw')
        cls.manager = User.objects.create_user('sem_mgr', password='pw')
        role = Role.objects.create(name='语义管理岗')
        role.permissions.add(
            Permission.objects.get(codename='structure_view'),
            Permission.objects.get(codename='blockchain_view'),
        )
        cls.manager.roles.add(role)

    def test_authenticated_without_perm_gets_403_page(self):
        """已登录但无权限码 → 403 品牌页（不再是 302 回工作台）。"""
        self.client.force_login(self.staff)
        response = self.client.get(PROTECTED)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, '权限不足', status_code=403)
        self.assertContains(response, '返回首页', status_code=403)

    def test_403_page_does_not_echo_exception_message(self):
        """页面只显示固定文案：异常 message 不进入 HTML（防泄漏内部细节）。"""
        self.client.force_login(self.staff)
        response = self.client.get(PROTECTED)
        self.assertNotContains(response, '无权访问该功能', status_code=403)

    def test_anonymous_still_redirects_to_login_with_next(self):
        """未登录语义不变：302 到登录页并带回 next。"""
        response = self.client.get(PROTECTED)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].startswith('/plugins/auth/login/'))
        self.assertIn('next=/plugins/structure/', response.headers['Location'])

    def test_json_403_by_accept_header(self):
        """带 `Accept: application/json` → JSON 错误体（不含 HTML）。"""
        self.client.force_login(self.staff)
        response = self.client.get(STATS_PATH, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'].split(';')[0], 'application/json')
        payload = response.json()
        self.assertEqual(payload['code'], 'permission_denied')
        self.assertEqual(payload['message'], '无权访问该功能')

    def test_json_403_by_path_suffix(self):
        """`/stats` 结尾即使不带 Accept 也走 JSON（与前端 fetch 的默认行为一致）。"""
        self.client.force_login(self.staff)
        response = self.client.get(STATS_PATH)
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload['code'], 'permission_denied')

    def test_rejection_is_logged_with_message(self):
        """日志里要能看出是哪个 message（原来只打 code，排查时不知道被哪条权限拦下）。"""
        self.client.force_login(self.staff)
        with self.assertLogs('plugin_host', level='WARNING') as captured:
            self.client.get(STATS_PATH)
        joined = '\n'.join(captured.output)
        self.assertIn('permission_denied', joined)
        self.assertIn('无权访问该功能', joined)

    def test_with_perm_still_200(self):
        """有权限用户不受影响。"""
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(PROTECTED).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('blockchain:blockchain_stats')).status_code, 200)
