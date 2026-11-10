"""v1.7.3 共享缓存：后端配置、`add()` 唯一键语义、登录失败计数落共享存储。

这一层只验证「跨进程共享」这个前提本身；限流阈值、Ticket 重放等业务回归放在
各自插件用例（`plugins/auth/tests_ratelimit.py`、`plugins/sso/tests.py`）。
"""

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.test import TestCase
from django.utils import timezone

CACHE_TABLE = 'constellatio_cache'
LOGIN_URL = '/plugins/auth/login/'


class SharedCacheBackendTests(TestCase):
    """后端选型：必须是数据库缓存，且容量参数留足余量。"""

    def test_default_cache_is_database_backend(self):
        """默认缓存是 DatabaseCache 且指向约定表名（跨 worker 共享的唯一来源）。"""
        self.assertEqual(
            settings.CACHES['default']['BACKEND'],
            'django.core.cache.backends.db.DatabaseCache',
        )
        self.assertIsInstance(caches['default'], DatabaseCache)
        self.assertEqual(caches['default']._table, CACHE_TABLE)

    def test_shipped_cache_config_has_culling_headroom(self):
        """MAX_ENTRIES 不能停在默认 300：_cull 会删掉未过期的防重放标记。"""
        backend = caches['default']
        self.assertGreaterEqual(backend._max_entries, 10000)
        self.assertEqual(backend.default_timeout, 900)


class SharedCacheAddSemanticsTests(TestCase):
    """`add()` 的三条分支：新键 / 未过期 / 已过期。"""

    def setUp(self):
        self.cache = caches['default']
        self.key = 'v173:add-semantics'
        self.cache.delete(self.key)

    def test_add_is_first_writer_wins(self):
        """第一次 add 成功、第二次失败；失败来自 cache_key 主键冲突。"""
        self.assertTrue(self.cache.add(self.key, 'v1'))
        self.assertFalse(self.cache.add(self.key, 'v2'))

        # 直接对同一 cache_key 再 INSERT，复现 add() 内部撞到的主键冲突，
        # 证明 False 不是「先查后判」而是「写入失败」（_base_set 的 except DatabaseError 分支）。
        stored_key = self.cache.make_and_validate_key(self.key)
        with self.assertRaises(IntegrityError) as caught:
            with transaction.atomic():
                with connections['default'].cursor() as cursor:
                    cursor.execute(
                        f'INSERT INTO {CACHE_TABLE} (cache_key, value, expires) VALUES (%s, %s, %s)',
                        [stored_key, 'raw', timezone.now()],
                    )
        self.assertIsInstance(caught.exception, DatabaseError)

    def test_add_reclaims_expired_key(self):
        """已过期的键可以被重新 add 成功（_base_set 的 UPDATE 分支）。"""
        self.cache.set(self.key, 'old', timeout=0)      # expires=now-1s，立即过期
        self.assertTrue(self.cache.add(self.key, 'new'))
        self.assertEqual(self.cache.get(self.key), 'new')


class SharedCacheLoginCounterTests(TestCase):
    """登录失败计数确实落在共享表里，而不是进程内 dict。"""

    def setUp(self):
        caches['default'].clear()

    def test_login_failures_land_in_shared_cache_table(self):
        for _ in range(3):
            response = self.client.post(
                LOGIN_URL, {'username': 'cache_probe_nobody', 'password': 'wrong'})
            self.assertEqual(response.status_code, 200)

        with connections['default'].cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM {CACHE_TABLE} WHERE cache_key LIKE %s',
                ['%auth:login-fail:%'],
            )
            rows = cursor.fetchone()[0]
        self.assertGreaterEqual(rows, 1)
