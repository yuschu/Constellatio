"""v1.7.x 留痕链并发加固 + 信号隔离测试（新增，不改既有 tests.py）。

覆盖：
- append() 在事务/行锁内追加后 prev_hash / record_hash 连续且可 verify；
- 同一 payload 连续追加两条不撞唯一键、链不分叉；
- 唯一键并发冲突时 append() 回滚并重试一次；
- 订阅方 handler 抛异常时上游审批流转 / 打卡仍然成功（信号隔离）。
"""

import hashlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plugins.approval import services
from plugins.approval.models import Approval

from .models import BlockchainRecord

User = get_user_model()


class AppendChainTests(TestCase):
    def test_append_keeps_chain_continuous_and_verifiable(self):
        records = [
            BlockchainRecord.append('approval', 'approval_finished', '1:approved'),
            BlockchainRecord.append('notice', 'notice_published', 'announcement:3'),
            BlockchainRecord.append('attendance', 'attendance_checked', '1:2026-10-27'),
        ]
        prev = '0' * 64
        for record in records:
            self.assertEqual(record.prev_hash, prev)
            self.assertEqual(
                record.record_hash,
                hashlib.sha256((prev + record.payload_hash).encode()).hexdigest())
            prev = record.record_hash
        self.assertTrue(BlockchainRecord.verify_chain()[0])
        self.assertTrue(all(len(r.record_hash) == 64 for r in records))

    def test_same_payload_twice_does_not_conflict(self):
        """并发同 payload：两条记录 prev 不同 → record_hash 不同，链仍连续。"""
        first = BlockchainRecord.append('user', 'user_created', 'user:7')
        second = BlockchainRecord.append('user', 'user_created', 'user:7')
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.record_hash, second.record_hash)
        self.assertEqual(first.payload_hash, second.payload_hash)
        self.assertEqual(second.prev_hash, first.record_hash)
        ok, broken = BlockchainRecord.verify_chain()
        self.assertTrue(ok)
        self.assertIsNone(broken)

    def test_append_retries_once_on_unique_conflict(self):
        """首次插入撞唯一键（并发同 payload）→ 重读链尾后重试成功。"""
        real_create = BlockchainRecord.objects.create
        calls = {'count': 0}

        def flaky_create(**kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                raise IntegrityError('duplicate record_hash')
            return real_create(**kwargs)

        with mock.patch.object(BlockchainRecord.objects, 'create',
                               side_effect=flaky_create):
            record = BlockchainRecord.append(
                'approval', 'approval_finished', '1:approved')
        self.assertEqual(calls['count'], 2)
        self.assertTrue(BlockchainRecord.objects.filter(pk=record.pk).exists())
        self.assertTrue(BlockchainRecord.verify_chain()[0])

    def test_append_reraises_after_second_conflict(self):
        """连续两次唯一键冲突：不再吞异常（重试上限一次）。"""
        with mock.patch.object(BlockchainRecord.objects, 'create',
                               side_effect=IntegrityError('duplicate')):
            with self.assertRaises(IntegrityError):
                BlockchainRecord.append('approval', 'approval_finished', '1:approved')


class SignalIsolationTests(TestCase):
    """订阅方（留痕 / 站内信）handler 抛异常时，上游业务不得失败。"""

    @classmethod
    def setUpTestData(cls):
        cls.applicant = User.objects.create_user('iso_applicant', password='pw')
        cls.approver = User.objects.create_user('iso_approver', password='pw')

    def _approval(self):
        return Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='隔离测试',
            applicant=self.applicant, approver=self.approver,
            status=Approval.Status.DRAFT)

    def test_approval_flow_survives_handler_failures(self):
        approval = self._approval()
        with self.assertLogs(level='ERROR') as captured, \
                mock.patch.object(BlockchainRecord, 'append',
                                  side_effect=RuntimeError('ledger down')), \
                mock.patch('plugins.notify.apps._bulk_create',
                           side_effect=RuntimeError('notify down')):
            services.submit(approval, operator=self.applicant)
            services.approve(approval, operator=self.approver)
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)
        self.assertFalse(BlockchainRecord.objects.exists())
        # 订阅方异常被 logger.exception 记录，而不是抛给上游
        self.assertGreaterEqual(len(captured.records), 2)

    def test_attendance_check_survives_ledger_failure(self):
        from plugins.attendance.models import Attendance

        self.client.force_login(self.applicant)
        with self.assertLogs(level='ERROR') as captured, \
                mock.patch.object(BlockchainRecord, 'append',
                                  side_effect=RuntimeError('ledger down')):
            response = self.client.post(reverse('attendance:attendance_check'),
                                        {'action': 'in', 'sign_type': 'internal'})
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(len(captured.records), 1)
        record = Attendance.objects.get(
            user=self.applicant, date=timezone.localdate())
        self.assertIsNotNone(record.check_in)
