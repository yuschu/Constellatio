"""v1.7.15 / 7.3：登出入口必须是 POST。

此前 `logout/` 是 GET：第三方页面一张 `<img src="/plugins/auth/logout/">` 就能把人踢下线
（CSRF 对 GET 天然无效）。改成 `@require_POST` + 导航里的带 CSRF 表单按钮后：
- GET → 405，会话不受影响；
- POST → 302 且会话失效（再访问受控页跳登录）。
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

LOGOUT_URL = '/plugins/auth/logout/'
PROTECTED_URL = '/plugins/user/profile/'   # 登录即可访问，不依赖权限码（v1.7.9 起无权限是 403）


class LogoutMethodTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('logout_probe', password='Logout@2026')

    def test_get_logout_is_rejected_and_session_kept(self):
        """GET 登出 → 405，且会话仍然有效（这正是被 <img src> 踢下线的那个洞）。"""
        self.client.force_login(self.user)
        response = self.client.get(LOGOUT_URL)
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
        # 受控页仍可访问（未被踢下线）
        self.assertEqual(self.client.get(PROTECTED_URL).status_code, 200)

    def test_post_logout_clears_session(self):
        """POST 登出 → 302，且会话失效：再访问受控页 302 到登录页。"""
        self.client.force_login(self.user)
        response = self.client.post(LOGOUT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

        after = self.client.get(PROTECTED_URL)
        self.assertEqual(after.status_code, 302)
        self.assertIn('/plugins/auth/login/', after.headers['Location'])
