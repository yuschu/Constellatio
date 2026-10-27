"""审批授权回归（v1.7.1 / P0-9、P0-10、P1-20、P1-25）。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Approval
from .views import _overtime_choices

User = get_user_model()


def _grant(user, codename):
    user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


class ApprovalObjectPermissionTests(TestCase):
    """P0-9：详情 / 附件只对单据相关人开放，approval_view 不再是通行证。"""

    @classmethod
    def setUpTestData(cls):
        cls.applicant = User.objects.create_user('alice', password='pw')
        cls.approver = User.objects.create_user('bob', password='pw')
        cls.cc_user = User.objects.create_user('carol', password='pw')
        cls.signer = User.objects.create_user('dave', password='pw')
        # 具备 L3 approval_view 但与单据无关的普通员工
        cls.stranger = _grant(User.objects.create_user('eve', password='pw'),
                              'approval_view')

    def setUp(self):
        cache.clear()

    def _approval(self, **kwargs):
        fields = {
            'approval_type': Approval.Type.LEAVE,
            'title': '请假：家事',
            'applicant': self.applicant,
            'approver': self.approver,
        }
        fields.update(kwargs)
        return Approval.objects.create(**fields)

    def test_stranger_cannot_view_detail(self):
        approval = self._approval()
        self.client.force_login(self.stranger)
        resp = self.client.get(
            reverse('approval:approval_detail', args=[approval.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/')

    def test_involved_users_can_view_detail(self):
        approval = self._approval()
        approval.cc_users.add(self.cc_user)
        for user in (self.applicant, self.approver, self.cc_user):
            self.client.force_login(user)
            resp = self.client.get(
                reverse('approval:approval_detail', args=[approval.pk]))
            self.assertEqual(resp.status_code, 200, msg=user.username)
            self.assertContains(resp, '请假：家事')

    def test_counter_signature_signer_can_view_detail(self):
        approval = self._approval(approval_type=Approval.Type.DEPT_DELETE, biz_id=1)
        approval.signers.create(signer=self.signer)
        self.client.force_login(self.signer)
        resp = self.client.get(
            reverse('approval:approval_detail', args=[approval.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_stranger_cannot_download_attachment(self):
        approval = self._approval()
        self.client.force_login(self.stranger)
        resp = self.client.get(
            reverse('approval:approval_attachment', args=[approval.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/')

    def test_involved_user_without_file_goes_to_detail(self):
        approval = self._approval()
        self.client.force_login(self.applicant)
        resp = self.client.get(
            reverse('approval:approval_attachment', args=[approval.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp['Location'],
            reverse('approval:approval_detail', args=[approval.pk]))


class ApprovalActPermissionTests(TestCase):
    """P0-10：具备 approval_approve 也不能审批别人的单。"""

    @classmethod
    def setUpTestData(cls):
        cls.applicant = User.objects.create_user('alice2', password='pw')
        cls.approver = User.objects.create_user('bob2', password='pw')
        cls.manager = _grant(User.objects.create_user('mgr2', password='pw'),
                             'approval_approve')
        cls.admin = User.objects.create_superuser('root2', '', 'rootpass')

    def setUp(self):
        cache.clear()

    def _pending(self):
        return Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假：审批路由',
            applicant=self.applicant, approver=self.approver,
            status=Approval.Status.PENDING)

    def test_manager_with_perm_cannot_approve_others(self):
        approval = self._pending()
        self.client.force_login(self.manager)
        self.client.post(
            reverse('approval:approval_detail', args=[approval.pk]),
            {'action': 'approve', 'comment': '越权审批'})
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.PENDING)
        self.assertEqual(approval.records.count(), 0)

    def test_designated_approver_can_approve(self):
        approval = self._pending()
        self.client.force_login(self.approver)
        self.client.post(
            reverse('approval:approval_detail', args=[approval.pk]),
            {'action': 'approve', 'comment': '同意'})
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)

    def test_superuser_can_approve_any(self):
        approval = self._pending()
        self.client.force_login(self.admin)
        self.client.post(
            reverse('approval:approval_detail', args=[approval.pk]),
            {'action': 'approve'})
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)


class ApprovalListPaginationTests(TestCase):
    """P1-20：列表 25 条/页，总数与页数正确。"""

    @classmethod
    def setUpTestData(cls):
        cls.applicant = _grant(
            User.objects.create_user('lister', password='pw'), 'approval_view')
        Approval.objects.bulk_create([
            Approval(approval_type=Approval.Type.LEAVE, title=f'请假 {i}',
                     applicant=cls.applicant)
            for i in range(30)
        ])

    def test_first_page_has_25_and_second_has_5(self):
        self.client.force_login(self.applicant)
        page1 = self.client.get(reverse('approval:approval_list'))
        self.assertEqual(len(page1.context['approvals']), 25)
        self.assertEqual(page1.context['total'], 30)
        page2 = self.client.get(reverse('approval:approval_list') + '?page=2')
        self.assertEqual(len(page2.context['approvals']), 5)
        self.assertEqual(page2.context['page_obj'].number, 2)


class OvertimeBasisTests(TestCase):
    """P1-25：调休依据只包含已通过且一年内的加班单。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('ot', password='pw')

    def _overtime(self, status, created_at=None):
        approval = Approval.objects.create(
            approval_type=Approval.Type.OVERTIME, title='加班',
            applicant=self.user, approver=self.user, status=status)
        if created_at is not None:
            Approval.objects.filter(pk=approval.pk).update(created_at=created_at)
        return approval

    def test_only_approved_and_recent(self):
        approved = self._overtime(Approval.Status.APPROVED)
        pending = self._overtime(Approval.Status.PENDING)
        rejected = self._overtime(Approval.Status.REJECTED)
        old = self._overtime(
            Approval.Status.APPROVED,
            created_at=timezone.now() - timedelta(days=400))

        choices = dict(_overtime_choices(self.user))
        self.assertIn(str(approved.pk), choices)
        self.assertNotIn(str(pending.pk), choices)
        self.assertNotIn(str(rejected.pk), choices)
        self.assertNotIn(str(old.pk), choices)
