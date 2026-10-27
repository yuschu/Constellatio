"""留痕视图回归（v1.7.1 / P1-21）：校验结果快照缓存。"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase

from .models import BlockchainRecord
from .views import _verify_snapshot

User = get_user_model()


class BlockchainViewCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('chainviewer', password='pw')
        role = cls.viewer.roles.create(name='留痕只读')
        role.permissions.add(Permission.objects.get(codename='blockchain_view'))

    def setUp(self):
        cache.clear()
        self.client.force_login(self.viewer)

    def test_list_reuses_snapshot(self):
        """同一链状态下连续两次请求只做一次全链校验。"""
        BlockchainRecord.append('notice', 'notice_published', 'a:1')
        with mock.patch.object(
                BlockchainRecord, 'verify_chain',
                return_value=(True, None)) as mocked:
            self.client.get('/plugins/blockchain/')
            self.client.get('/plugins/blockchain/')
        self.assertEqual(mocked.call_count, 1)

    def test_snapshot_key_changes_after_append(self):
        """追加新记录会换缓存键，校验结果不会被旧快照复用。"""
        BlockchainRecord.append('notice', 'notice_published', 'a:1')
        with mock.patch.object(
                BlockchainRecord, 'verify_chain',
                return_value=(True, None)) as mocked:
            self.client.get('/plugins/blockchain/')
            BlockchainRecord.append('notice', 'notice_published', 'a:2')
            self.client.get('/plugins/blockchain/')
        self.assertEqual(mocked.call_count, 2)

    def test_force_bypasses_cache(self):
        """force=True 直接全量重算，能看到原地篡改。"""
        import hashlib

        record = BlockchainRecord.append('notice', 'notice_published', 'a:1')
        self.assertEqual(_verify_snapshot(), (True, None))
        BlockchainRecord.objects.filter(pk=record.pk).update(
            payload_hash=hashlib.sha256(b'evil').hexdigest())
        self.assertTrue(_verify_snapshot()[0])          # 缓存窗口内仍为旧结论
        ok, broken_id = _verify_snapshot(force=True)
        self.assertFalse(ok)
        self.assertEqual(broken_id, record.pk)
