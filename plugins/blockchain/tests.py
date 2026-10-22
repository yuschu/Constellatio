"""blockchain 单元测试：链式追加 / 完整性校验 / 篡改检测。"""

import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import BlockchainRecord

User = get_user_model()


class BlockchainTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('admin', password='pw')

    def test_append_links_chain(self):
        r1 = BlockchainRecord.append(
            'approval', 'approval_finished', '1:approved', operator=self.user)
        r2 = BlockchainRecord.append('notice', 'notice_published', 'a:3')
        self.assertEqual(r1.prev_hash, '0' * 64)
        self.assertEqual(r2.prev_hash, r1.record_hash)  # 串链
        self.assertEqual(len(r2.record_hash), 64)

    def test_record_hash_algorithm(self):
        payload = 'x'
        r = BlockchainRecord.append('approval', 'approval_finished', payload)
        expect = hashlib.sha256(
            (('0' * 64) + hashlib.sha256(payload.encode()).hexdigest()).encode()).hexdigest()
        self.assertEqual(r.record_hash, expect)

    def test_verify_ok(self):
        BlockchainRecord.append('approval', 'approval_finished', '1:approved')
        BlockchainRecord.append('notice', 'notice_published', 'a:3')
        ok, broken = BlockchainRecord.verify_chain()
        self.assertTrue(ok)
        self.assertIsNone(broken)

    def test_verify_detects_tamper(self):
        BlockchainRecord.append('approval', 'approval_finished', '1:approved')
        r2 = BlockchainRecord.append('notice', 'notice_published', 'a:3')
        # 篡改第二条 payload
        BlockchainRecord.objects.filter(pk=r2.pk).update(
            payload_hash=hashlib.sha256(b'evil').hexdigest())
        ok, broken = BlockchainRecord.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(broken, r2.id)

    def test_list_links_to_record_detail(self):
        self.client.force_login(self.user)
        record = BlockchainRecord.append(
            'approval', 'approval_finished', '1:approved', operator=self.user)
        response = self.client.get('/plugins/blockchain/')
        self.assertContains(response, f'/plugins/blockchain/{record.id}/')

    def test_record_detail(self):
        self.client.force_login(self.user)
        record = BlockchainRecord.append(
            'approval', 'approval_finished', '1:approved', operator=self.user)
        response = self.client.get(f'/plugins/blockchain/{record.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, record.record_hash)
        self.assertContains(response, record.prev_hash)
        self.assertContains(response, '操作记录')
