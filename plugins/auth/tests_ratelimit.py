"""登录限流（v1.7.1 / P1-14 → v1.7.7 / P2 计数原子化）。

计数存储从「共享缓存 get+set」换成「独立计数表 + select_for_update」。
注意：sqlite 上 `select_for_update()` **静默退化**（不加 FOR UPDATE、不报错），
所以本文件的用例只验证顺序语义（阈值 / 清零 / 隔离 / 窗口重置），
**不验证锁**——并发证据只在容器 MySQL 上跑（见 docs/plugin-dev-v177.md §五）。
"""

import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import LoginFailureCounter
from .views import LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW, _fail_key, _record_failure

User = get_user_model()

LOGIN_URL = '/plugins/auth/login/'


class LoginRateLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('rl_user', password='rightpass123')

    def setUp(self):
        LoginFailureCounter.objects.all().delete()

    def _post(self, password='wrong-pass', username='rl_user'):
        return self.client.post(LOGIN_URL, {'username': username, 'password': password})

    def _counter(self, username='rl_user', ip='127.0.0.1'):
        key = hashlib.sha256(f'{username.lower()}|{ip}'.encode('utf-8')).hexdigest()[:32]
        return LoginFailureCounter.objects.filter(key=key).first()

    def test_lockout_after_limit_failures(self):
        """前 4 次提示密码错误；第 5 次达阈值当次即提示锁定；第 6 次即使密码正确也先被拦。"""
        for index in range(1, LOGIN_FAIL_LIMIT + 1):
            resp = self._post()
            self.assertEqual(resp.status_code, 200)
            if index < LOGIN_FAIL_LIMIT:
                self.assertContains(resp, '用户名或密码错误')
            else:
                # v1.7.7：计数在本次累加后达到阈值 → 当次就回锁定提示（不再等下一次请求）
                self.assertContains(resp, '尝试次数过多')
        self.assertEqual(self._counter().count, LOGIN_FAIL_LIMIT)

        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '尝试次数过多')
        self.assertNotIn('_auth_user_id', self.client.session)
        # 被拦的请求不累加计数（封顶在阈值）
        self.assertEqual(self._counter().count, LOGIN_FAIL_LIMIT)

    def test_success_below_limit_logs_in_and_deletes_counter(self):
        """未达阈值时正确密码可登录，并删掉计数行（替代旧的 cache.delete）。"""
        for _ in range(3):
            self._post()
        counter = self._counter()
        self.assertIsNotNone(counter)
        self.assertEqual(counter.count, 3)

        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertFalse(LoginFailureCounter.objects.filter(pk=counter.pk).exists())

        self.client.logout()
        for _ in range(4):
            self._post()
        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 302)

    def test_different_users_do_not_share_counter(self):
        """限流按用户名 + IP 隔离，不能因为别人失败而锁自己。"""
        for _ in range(LOGIN_FAIL_LIMIT):
            self._post(username='nobody')
        resp = self._post('rightpass123', username='rl_user')
        self.assertEqual(resp.status_code, 302)

    def test_counter_increments_on_each_failure(self):
        """每次失败计数 +1，窗口起点不变（同一窗口内累加）。"""
        self._post()
        first = self._counter()
        self.assertEqual(first.count, 1)
        started = first.window_started_at

        self._post()
        second = self._counter()
        self.assertEqual(second.count, 2)
        self.assertEqual(second.window_started_at, started)

    def test_window_expiry_resets_counter(self):
        """窗口过期后下一次失败重新从 1 开始，并刷新窗口起点。"""
        for _ in range(3):
            self._post()
        counter = self._counter()
        self.assertEqual(counter.count, 3)

        # 把窗口推到过期（不用 sleep，直接改时间戳）
        counter.window_started_at = timezone.now() - timedelta(seconds=LOGIN_FAIL_WINDOW + 1)
        counter.save(update_fields=['window_started_at'])

        request = type('Req', (), {'META': {'REMOTE_ADDR': '127.0.0.1'}})()
        _record_failure(request, 'rl_user')
        counter.refresh_from_db()
        self.assertEqual(counter.count, 1)
        self.assertGreater(counter.window_started_at,
                           timezone.now() - timedelta(seconds=LOGIN_FAIL_WINDOW))

    def test_threshold_blocks_even_with_correct_password(self):
        """计数已达阈值时，正确密码同样被拦（直接构造计数行，不依赖 5 次请求）。"""
        key = _fail_key(
            type('Req', (), {'META': {'REMOTE_ADDR': '127.0.0.1'}})(), 'rl_user')
        LoginFailureCounter.objects.create(
            key=key, count=LOGIN_FAIL_LIMIT, window_started_at=timezone.now())

        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '尝试次数过多')
        self.assertNotIn('_auth_user_id', self.client.session)
        # 被拦时不应再累加计数
        self.assertEqual(LoginFailureCounter.objects.get(key=key).count, LOGIN_FAIL_LIMIT)

    def test_expired_window_does_not_lock(self):
        """窗口已过期的旧计数不能继续锁人。"""
        key = _fail_key(
            type('Req', (), {'META': {'REMOTE_ADDR': '127.0.0.1'}})(), 'rl_user')
        LoginFailureCounter.objects.create(
            key=key, count=LOGIN_FAIL_LIMIT,
            window_started_at=timezone.now() - timedelta(seconds=LOGIN_FAIL_WINDOW + 10))

        resp = self._post('rightpass123')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)
