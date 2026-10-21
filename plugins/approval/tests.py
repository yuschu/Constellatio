"""approval 状态机单元测试（必写：所有流转路径 + 信号）。"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from plugin_host.signals import approval_finished

from .models import Approval
from .services import approve, reject, submit

User = get_user_model()


class ApprovalFlowTest(TestCase):
    def setUp(self):
        self.applicant = User.objects.create_user('alice', password='pw')
        self.approver = User.objects.create_user('bob', password='pw')

    def _approval(self):
        return Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.applicant, approver=self.approver)

    def test_submit_promotes_to_pending(self):
        a = self._approval()
        submit(a, self.applicant)
        a.refresh_from_db()
        self.assertEqual(a.status, Approval.Status.PENDING)
        self.assertEqual(a.records.count(), 1)

    def test_approve_only_from_pending(self):
        a = self._approval()
        with self.assertRaises(ValueError):
            approve(a, self.approver)
        submit(a, self.applicant)
        approve(a, self.approver, 'OK')
        a.refresh_from_db()
        self.assertEqual(a.status, Approval.Status.APPROVED)
        self.assertEqual(a.records.count(), 2)

    def test_reject(self):
        a = self._approval()
        submit(a, self.applicant)
        reject(a, self.approver, 'NO')
        a.refresh_from_db()
        self.assertEqual(a.status, Approval.Status.REJECTED)
        self.assertEqual(a.records.count(), 2)

    def test_double_approve_rejected(self):
        a = self._approval()
        submit(a, self.applicant)
        approve(a, self.approver)
        with self.assertRaises(ValueError):
            approve(a, self.approver)

    def test_approve_emits_signal(self):
        received = []
        approval_finished.connect(
            lambda sender, **kw: received.append(kw), weak=False)
        a = self._approval()
        submit(a, self.applicant)
        approve(a, self.approver)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['result'], 'approved')
        self.assertEqual(received[0]['approval_id'], a.id)
