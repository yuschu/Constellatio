"""v1.5.5 工作台与侧栏高亮测试。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from plugins.approval.models import Approval
from plugins.attendance.models import Attendance
from plugins.notice.models import Announcement
from plugins.user.models import Role

User = get_user_model()
P = Permission.objects


def grant(user, *codes):
    role = Role.objects.create(name=f'role-{user.username}')
    for code in codes:
        role.permissions.add(P.get(codename=code))
    user.roles.add(role)
    return role


class WorkbenchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('staff', '', 'pw', last_name='员工')
        grant(cls.staff, 'approval_view')
        cls.admin = User.objects.create_superuser('root', '', 'pw')

    def test_employee_view_has_no_plugin_ops(self):
        self.client.force_login(self.staff)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '员工视图')
        self.assertContains(response, '待办聚合')
        self.assertContains(response, '流程快捷发起')
        self.assertContains(response, '公告简报')
        self.assertNotContains(response, '插件运维')
        self.assertNotContains(response, '打开插件开关')

    def test_admin_view_shows_plugin_ops(self):
        self.client.force_login(self.admin)
        response = self.client.get('/')
        self.assertContains(response, '管理员视图')
        self.assertContains(response, '插件运维')
        self.assertContains(response, '已启用插件')
        self.assertContains(response, '/plugins/workspace/')

    def test_pending_count(self):
        manager = User.objects.create_user('mgr_pending', '', 'pw', last_name='经理')
        grant(manager, 'approval_view', 'approval_approve')
        Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.staff, approver=manager, status=Approval.Status.PENDING)
        # v1.5.15：L3 不显示待办计数
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/').context['pending_approvals'], 0)
        self.assertNotContains(self.client.get('/'), '/plugins/approval/pending/')
        # 管理岗可见并计数
        self.client.force_login(manager)
        self.assertEqual(self.client.get('/').context['pending_approvals'], 1)

    def test_attendance_todo_states(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get('/').context['attendance_today']['label'], '今日未签到')
        from django.utils import timezone
        Attendance.objects.create(user=self.staff, date=timezone.localdate())
        self.assertEqual(
            self.client.get('/').context['attendance_today']['label'], '今日未签到')

    def test_notices_latest_three(self):
        for i in range(5):
            Announcement.objects.create(
                title=f'N{i}', content='x', publisher=self.admin,
                is_top=(i == 4))
        self.client.force_login(self.staff)
        response = self.client.get('/')
        notices = response.context['notices']
        self.assertEqual(len(notices), 3)
        self.assertEqual(notices[0].title, 'N4')     # 置顶优先

    def test_shortcut_includes_attendance_report_for_manager(self):
        manager = User.objects.create_user('mgr', '', 'pw')
        grant(manager, 'attendance_report_view')
        self.client.force_login(manager)
        response = self.client.get('/')
        self.assertContains(response, '签到详情')
        self.assertContains(response, '/plugins/attendance/records/')

    def test_shortcut_falls_back_to_attendance_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get('/')
        self.assertContains(response, '我的考勤')
        self.assertNotContains(response, '/plugins/attendance/records/')


class MenuActiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('staff', '', 'pw')
        grant(cls.staff, 'approval_view')

    def test_current_tab_highlighted(self):
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/notice/')
        self.assertContains(response, 'href="/plugins/notice/" class="r-menu-link is-active"')

    def test_home_tab_highlighted(self):
        self.client.force_login(self.staff)
        response = self.client.get('/')
        self.assertContains(response, 'href="/" class="r-menu-link is-active"')

    def test_detail_page_highlights_parent_menu(self):
        approval = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.staff, approver=self.staff)
        self.client.force_login(self.staff)
        response = self.client.get(f'/plugins/approval/{approval.pk}/')
        self.assertContains(response, 'href="/plugins/approval/" class="r-menu-link is-active"')

    def test_exact_match_wins_over_parent(self):
        manager = User.objects.create_user('mgr', '', 'pw')
        grant(manager, 'attendance_report_view')
        self.client.force_login(manager)
        response = self.client.get('/plugins/attendance/records/')
        self.assertContains(
            response, 'href="/plugins/attendance/records/" class="r-menu-link is-active"')
        self.assertNotContains(
            response, 'href="/plugins/attendance/" class="r-menu-link is-active"')
