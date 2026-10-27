"""notify 站内信：产生 / 未读 / 已读 / 越权 / 停用降级。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from plugin_host.signals import notice_published
from plugins.approval import services
from plugins.approval.models import Approval
from plugins.notice.models import Announcement

from .models import Notification

User = get_user_model()


class NotificationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.applicant = User.objects.create_user('n_applicant', password='pw')
        cls.approver = User.objects.create_user('n_approver', password='pw')
        cls.other = User.objects.create_user('n_other', password='pw')
        cls.admin = User.objects.create_superuser('n_admin', '', 'pw')

    def _approval(self, **kwargs):
        defaults = {
            'approval_type': Approval.Type.LEAVE,
            'title': '测试请假',
            'applicant': self.applicant,
            'approver': self.approver,
            'status': Approval.Status.DRAFT,
        }
        defaults.update(kwargs)
        return Approval.objects.create(**defaults)

    def test_submit_notifies_approver(self):
        approval = self._approval()
        services.submit(approval, operator=self.applicant)
        messages = Notification.objects.filter(recipient=self.approver)
        self.assertEqual(messages.count(), 1)
        message = messages.first()
        self.assertEqual(message.category, Notification.Category.APPROVAL)
        self.assertIn('测试请假', message.title)
        self.assertEqual(message.link, f'/plugins/approval/{approval.pk}/')
        # 申请人本人不收到待办
        self.assertFalse(Notification.objects.filter(recipient=self.applicant).exists())

    def test_finish_notifies_applicant(self):
        approval = self._approval()
        services.submit(approval, operator=self.applicant)
        services.approve(approval, operator=self.approver)
        message = Notification.objects.filter(
            recipient=self.applicant, category='approval').first()
        self.assertIsNotNone(message)
        self.assertIn('已通过', message.title)

    def test_notice_published_fanout(self):
        announcement = Announcement.objects.create(
            title='全员公告', content='正文', publisher=self.admin)
        notice_published.send(
            sender=Announcement, announcement_id=announcement.pk)
        recipients = set(Notification.objects.filter(
            category='notice').values_list('recipient__username', flat=True))
        self.assertEqual(recipients, {'n_applicant', 'n_approver', 'n_other'})
        self.assertNotIn('n_admin', recipients)   # 发布人不给自己发提醒

    def test_list_only_own_and_filter_unread(self):
        Notification.objects.create(recipient=self.other, title='他人消息')
        Notification.objects.create(recipient=self.applicant, title='我的消息')
        self.client.force_login(self.applicant)
        response = self.client.get(reverse('notify:notify_list'))
        self.assertContains(response, '我的消息')
        self.assertNotContains(response, '他人消息')
        response = self.client.get(reverse('notify:notify_list'), {'status': 'unread'})
        self.assertContains(response, '我的消息')

    def test_read_marks_and_redirects(self):
        message = Notification.objects.create(
            recipient=self.applicant, title='审批待办',
            link='/plugins/approval/1/')
        self.client.force_login(self.applicant)
        response = self.client.get(reverse('notify:notify_read', args=[message.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/plugins/approval/1/')
        message.refresh_from_db()
        self.assertTrue(message.is_read)
        self.assertIsNotNone(message.read_at)

    def test_read_others_message_404(self):
        message = Notification.objects.create(recipient=self.other, title='x')
        self.client.force_login(self.applicant)
        response = self.client.get(reverse('notify:notify_read', args=[message.pk]))
        self.assertEqual(response.status_code, 404)

    def test_external_link_not_followed(self):
        message = Notification.objects.create(
            recipient=self.applicant, title='x', link='https://evil.example.com/')
        self.client.force_login(self.applicant)
        response = self.client.get(reverse('notify:notify_read', args=[message.pk]))
        self.assertEqual(response['Location'], reverse('notify:notify_list'))

    def test_read_all(self):
        for index in range(3):
            Notification.objects.create(recipient=self.applicant, title=f'm{index}')
        self.client.force_login(self.applicant)
        response = self.client.post(reverse('notify:notify_read_all'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(
            recipient=self.applicant, is_read=False).count(), 0)

    def test_unread_badge_in_nav(self):
        Notification.objects.create(recipient=self.applicant, title='未读消息')
        self.client.force_login(self.applicant)
        response = self.client.get('/')
        self.assertContains(response, '消息中心')
        self.assertEqual(response.context['notify_unread'], 1)

    def test_plugin_disabled_hides_entry(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notify', enabled=False)
        Notification.objects.create(recipient=self.applicant, title='未读消息')
        self.client.force_login(self.applicant)
        response = self.client.get('/')
        self.assertNotContains(response, reverse('notify:notify_list'))
