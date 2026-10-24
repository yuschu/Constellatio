"""工作台图表大盘与侧栏高亮测试（v1.5.5 起，v1.6.2 扩展）。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from plugins.approval.models import Approval
from plugins.attendance.models import Attendance
from plugins.blockchain.models import BlockchainRecord
from plugins.notice.models import Announcement
from plugins.user.models import Department, Role

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

    def test_employee_view_has_no_global_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '员工视图')
        self.assertContains(response, '核心数据看板')
        self.assertContains(response, '流程快捷发起')
        self.assertContains(response, '公告简报')
        self.assertNotContains(response, '插件运行状态')
        self.assertNotContains(response, '插件运维与组织数据')
        self.assertNotContains(response, '打开插件开关')

    def test_admin_view_shows_global_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get('/')
        self.assertContains(response, '管理员视图')
        self.assertContains(response, '核心数据看板')
        self.assertContains(response, '插件运行状态')
        self.assertContains(response, '插件运维与组织数据')
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


class DashboardDataTests(TestCase):
    """v1.6.2：范围筛选 / 角色分流 / 告警 / 降级 / 图表 payload。"""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('dashstaff', '', 'pw', last_name='员工')
        grant(cls.staff, 'approval_view')
        cls.other = User.objects.create_user('dashother', '', 'pw', last_name='同事')
        grant(cls.other, 'approval_view')
        cls.manager = User.objects.create_user('dashmgr', '', 'pw', last_name='经理')
        grant(cls.manager, 'approval_view', 'approval_approve')
        cls.admin = User.objects.create_superuser('dashroot', '', 'pw')

        cls.leave = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=cls.staff, approver=cls.manager,
            status=Approval.Status.PENDING)
        cls.expense = Approval.objects.create(
            approval_type=Approval.Type.EXPENSE, title='报销',
            applicant=cls.other, approver=cls.manager,
            status=Approval.Status.APPROVED)
        cls.seal = Approval.objects.create(
            approval_type=Approval.Type.SEAL, title='用章',
            applicant=cls.staff, approver=cls.manager,
            status=Approval.Status.APPROVED)

        cls.dept = Department.objects.create(name='研发部', is_active=True)
        cls.staff.department = cls.dept
        cls.staff.save(update_fields=['department'])
        Attendance.objects.create(
            user=cls.staff, date=timezone.localdate(),
            check_in=timezone.now())
        BlockchainRecord.append('user', 'user_created', 'dash:1')

    def test_employee_scope_only_own_requests(self):
        self.client.force_login(self.staff)
        response = self.client.get('/')
        flow = response.context['cards']['flow']
        self.assertEqual(flow['total'], 2)   # 请假 + 用章，均本人发起
        self.assertContains(response, '核心数据看板')
        self.assertNotContains(response, '插件分布')

        self.client.force_login(self.admin)
        admin_flow = self.client.get('/').context['cards']['flow']
        self.assertEqual(admin_flow['total'], 3)

    def test_range_filter_and_bucket_axis(self):
        self.client.force_login(self.staff)
        response = self.client.get('/', {'range': 'week'})
        self.assertEqual(response.context['range_key'], 'week')
        self.assertEqual(len(response.context['trend']['categories']), 7)

        response = self.client.get('/', {'range': 'today'})
        self.assertEqual(len(response.context['trend']['categories']), 24)

        response = self.client.get('/', {'range': 'bogus'})
        self.assertEqual(response.context['range_key'], 'month')
        self.assertEqual(len(response.context['trend']['categories']), 30)

    def test_dashboard_payloads_and_links(self):
        self.client.force_login(self.staff)
        response = self.client.get('/')
        cards = response.context['cards']
        self.assertEqual(cards['approval']['payload']['link'],
                         '/plugins/approval/pending/')
        self.assertEqual(cards['flow']['payload']['link'], '/plugins/approval/')
        self.assertEqual(cards['attendance']['payload']['engine'], 'echarts')
        self.assertEqual(cards['attendance']['checked_days'], 1)
        trend = response.context['trend']
        self.assertEqual(len(trend['series']), 5)
        self.assertEqual(trend['payload']['link'], '/plugins/approval/')

    def test_approval_alert_on_many_pending(self):
        for _ in range(3):
            Approval.objects.create(
                approval_type=Approval.Type.LEAVE, title='待办',
                applicant=self.staff, approver=self.manager,
                status=Approval.Status.PENDING)
        self.client.force_login(self.manager)
        response = self.client.get('/')
        self.assertTrue(response.context['cards']['approval']['alert'])
        self.assertContains(response, '待办较多')

    def test_plugin_alert_when_plugin_disabled(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        self.client.force_login(self.admin)
        response = self.client.get('/')
        self.assertTrue(response.context['cards']['plugins']['alert'])
        self.assertContains(response, '插件未全部启用')

    def test_chart_disabled_degrades_to_numbers_and_tables(self):
        with override_settings(OA_CHARTS='none'):
            self.client.force_login(self.admin)
            response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'wb-chart-trend')
        self.assertIsNone(response.context['trend']['payload'])
        self.assertContains(response, '单据数')   # 降级表格表头

    def test_admin_pie_and_department_chart(self):
        self.client.force_login(self.admin)
        response = self.client.get('/')
        pie = response.context['pie']
        self.assertEqual(pie['total'], 1)
        self.assertEqual(pie['rows'][0]['label'], '用户与组织')
        dept = response.context['dept']
        self.assertEqual(dept['rows'][0]['name'], '研发部')
        self.assertEqual(dept['rows'][0]['headcount'], 1)


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
