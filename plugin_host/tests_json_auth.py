"""v1.7.11：匿名 + 要 JSON → 401 JSON；HTML 仍 302 到登录页。

背景：`fetch` 跟随 302 会拿到登录页 HTML，在 `response.json()` 处炸掉（图表只显示「不可用」）。
本文件的 5 条用例把 401 / 302 / 403 三种口径分开钉住，避免以后有人把登录守卫的
JSON 分支与权限的 403 混在一起。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from plugins.user.models import Role

User = get_user_model()

PROTECTED = '/plugins/structure/'
STATS_PATH = '/plugins/blockchain/stats/'
LOGIN_PREFIX = '/plugins/auth/login/'


class AnonymousJsonTests(TestCase):
    """匿名请求：要 JSON → 401；要 HTML → 302。"""

    def test_anonymous_json_by_accept_header(self):
        response = self.client.get(PROTECTED, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['Content-Type'].split(';')[0], 'application/json')
        payload = response.json()
        self.assertEqual(payload['code'], 'authentication_required')
        self.assertEqual(payload['message'], '登录状态已失效，请重新登录')

    def test_anonymous_json_by_path_suffix(self):
        """`/stats` 结尾即使不带 Accept 也走 401 JSON（与前端 fetch 约定一致）。"""
        response = self.client.get(STATS_PATH)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'authentication_required')

    def test_anonymous_html_still_redirects_with_next(self):
        """回归保护：HTML 语义不动（v1.7.4 口径）。"""
        response = self.client.get(PROTECTED)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].startswith(LOGIN_PREFIX))
        self.assertIn('next=/plugins/structure/', response.headers['Location'])

    def test_login_not_required_view_unaffected(self):
        """`login_not_required` 的入口不参与守卫（登录页本身匿名可访问）。"""
        response = self.client.get(LOGIN_PREFIX)
        self.assertEqual(response.status_code, 200)


class AuthenticatedJsonTests(TestCase):
    """已登录但无权限：仍是 403（不能与登录失效的 401 混）。"""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('json401_staff', password='pw')
        cls.manager = User.objects.create_user('json401_mgr', password='pw')
        role = Role.objects.create(name='401 语义管理岗')
        role.permissions.add(Permission.objects.get(codename='attendance_check'))
        cls.manager.roles.add(role)

    def test_authenticated_without_perm_is_403_not_401(self):
        self.client.force_login(self.staff)
        response = self.client.get(STATS_PATH, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload['code'], 'permission_denied')

    def test_attendance_check_when_permissions_frozen_is_403(self):
        """v1.7.11：手写 has_perm 的 `attendance_check` 由 302 改为 403。

        `attendance_check` 是全员基线权限（`plugins/user/perms.py`），普通员工永远有；
        唯一会被拒绝的真实状态是**权限冻结**（`permission_frozen=True`，has_perm 立即短路）。
        """
        self.staff.permission_frozen = True
        self.staff.save(update_fields=['permission_frozen'])
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/attendance/check/', {'action': 'in'})
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, '403', status_code=403)
