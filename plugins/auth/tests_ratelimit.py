"""登录限流（v1.7.1 / P1-14）：失败计数、阈值锁定、成功清零。"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

User = get_user_model()

LOGIN_URL = '/plugins/auth/login/'


class LoginRateLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('rl_user', password='rightpass123')

    def setUp(self):
        cache.clear()

    def _post(self, password='wrong-pass', username='rl_user'):
        return self.client.post(LOGIN_URL, {'username': username, 'password': password})

    def test_lockout_after_limit_failures(self):
        """5 次失败后第 6 次即使密码正确也先被拦，且不建立登录态。"""
        for _ in range(5):
            resp = self._post()
            self.assertEqual(resp.status_code, 200)
        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '尝试次数过多')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_success_below_limit_logs_in_and_resets_counter(self):
        """未达阈值时正确密码可登录，并清零失败计数。"""
        for _ in range(3):
            self._post()
        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

        self.client.logout()
        for _ in range(4):
            self._post()
        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 302)

    def test_different_users_do_not_share_counter(self):
        """限流按用户名 + IP 隔离，不能因为别人失败而锁自己。"""
        for _ in range(5):
            self._post(username='nobody')
        resp = self._post('rightpass123', username='rl_user')
        self.assertEqual(resp.status_code, 302)
