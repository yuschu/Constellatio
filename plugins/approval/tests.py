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


class CounterSignatureTest(TestCase):
    """v1.2 会签：全部通过才 approved；任一人驳回即 rejected；非会签人不能签。"""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.applicant = User.objects.create_user('alice', password='pw')
        cls.signer_a = User.objects.create_user('signa', password='pw')
        cls.signer_b = User.objects.create_user('signb', password='pw')
        cls.outsider = User.objects.create_user('outsider', password='pw')

    def _approval(self):
        from .models import Approval
        a = Approval.objects.create(
            approval_type=Approval.Type.DEPT_DELETE, title='删部门',
            applicant=self.applicant, approver=self.applicant, biz_id=1)
        return a

    def test_all_signs_approve_and_callback(self):
        from plugin_host.signals import counter_signature_approved

        from .models import Approval
        from .services import sign_approve, start_counter_signature
        received = []
        counter_signature_approved.connect(lambda sender, **kw: received.append(kw), weak=False)
        a = self._approval()
        start_counter_signature(a, [self.signer_a, self.signer_b], self.applicant)
        sign_approve(a, self.signer_a, '同意')
        a.refresh_from_db()
        self.assertEqual(a.status, Approval.Status.PENDING)     # 一人未签仍待审批
        sign_approve(a, self.signer_b, '同意')
        a.refresh_from_db()
        self.assertEqual(a.status, Approval.Status.APPROVED)
        self.assertEqual(received[-1]['biz_type'], 'dept_delete')
        self.assertEqual(received[-1]['biz_id'], 1)

    def test_any_reject_rejects(self):
        from .models import Approval
        from .services import sign_reject, start_counter_signature
        a = self._approval()
        start_counter_signature(a, [self.signer_a, self.signer_b], self.applicant)
        sign_reject(a, self.signer_a, '不同意')
        a.refresh_from_db()
        self.assertEqual(a.status, Approval.Status.REJECTED)

    def test_outsider_cannot_sign(self):
        from .services import sign_approve, start_counter_signature
        a = self._approval()
        start_counter_signature(a, [self.signer_a], self.applicant)
        with self.assertRaises(ValueError):
            sign_approve(a, self.outsider)

    def test_start_without_signers_raises(self):
        from .services import start_counter_signature
        a = self._approval()
        with self.assertRaises(ValueError):
            start_counter_signature(a, [], self.applicant)
