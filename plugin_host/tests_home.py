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
        response = self.client.get('/dashboard/')
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
        response = self.client.get('/dashboard/')
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
        self.assertEqual(self.client.get('/dashboard/').context['pending_approvals'], 0)
        self.assertNotContains(self.client.get('/dashboard/'), '/plugins/approval/pending/')
        # 管理岗可见并计数
        self.client.force_login(manager)
        self.assertEqual(self.client.get('/dashboard/').context['pending_approvals'], 1)

    def test_attendance_todo_states(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get('/dashboard/').context['attendance_today']['label'], '今日未签到')
        Attendance.objects.create(user=self.staff, date=timezone.localdate())
        self.assertEqual(
            self.client.get('/dashboard/').context['attendance_today']['label'], '今日未签到')

    def test_notices_latest_three(self):
        for i in range(5):
            Announcement.objects.create(
                title=f'N{i}', content='x', publisher=self.admin,
                is_top=(i == 4))
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        notices = response.context['notices']
        self.assertEqual(len(notices), 3)
        self.assertEqual(notices[0].title, 'N4')     # 置顶优先

    def test_shortcut_includes_attendance_report_for_manager(self):
        manager = User.objects.create_user('mgr', '', 'pw')
        grant(manager, 'attendance_report_view')
        self.client.force_login(manager)
        response = self.client.get('/dashboard/')
        self.assertContains(response, '签到详情')
        self.assertContains(response, '/plugins/attendance/records/')

    def test_shortcut_falls_back_to_attendance_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
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
        response = self.client.get('/dashboard/')
        flow = response.context['cards']['flow']
        self.assertEqual(flow['total'], 2)   # 请假 + 用章，均本人发起
        self.assertContains(response, '核心数据看板')
        self.assertNotContains(response, '插件分布')

        self.client.force_login(self.admin)
        admin_flow = self.client.get('/dashboard/').context['cards']['flow']
        self.assertEqual(admin_flow['total'], 3)

    def test_range_filter_and_bucket_axis(self):
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/', {'range': 'week'})
        self.assertEqual(response.context['range_key'], 'week')
        self.assertEqual(len(response.context['trend']['categories']), 7)

        response = self.client.get('/dashboard/', {'range': 'today'})
        self.assertEqual(len(response.context['trend']['categories']), 24)

        response = self.client.get('/dashboard/', {'range': 'bogus'})
        self.assertEqual(response.context['range_key'], 'month')
        self.assertEqual(len(response.context['trend']['categories']), 30)

    def test_range_links_stay_on_current_page(self):
        """v2.1.9：范围切换留在当前页——原来写死 /?range=…，点一下就离开看板。"""
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        # 默认 range=month 那一格是 aria-current 的 span，只有另外两格带 href
        self.assertContains(response, 'href="/dashboard/?range=today"')
        self.assertContains(response, 'href="/dashboard/?range=week"')
        self.assertNotContains(response, 'href="/?range=')

        response = self.client.get('/', {'panel': 'dashboard'})
        self.assertEqual(response.context['panel'], 'dashboard')
        self.assertContains(response, 'href="/?panel=dashboard&amp;range=today"')
        self.assertContains(response, 'href="/?panel=dashboard&amp;range=week"')
        # 范围切换走原地替换，脚本在首页与业务页都要带上
        self.assertContains(response, 'js/dashboard-range.js')

    def test_dashboard_payloads_and_links(self):
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
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
        response = self.client.get('/dashboard/')
        self.assertTrue(response.context['cards']['approval']['alert'])
        self.assertContains(response, '待办较多')

    def test_employee_gets_fifth_kpi_instead_of_approval(self):
        """没有 approval_approve 的账号看不到「待我审批」，第一格换成「我的待处理」。

        KPI 恒为 5 张，3 列网格不留空位（DSH 的 kpis 是 repeat(3, ...)）。
        """
        for status in (Approval.Status.PENDING, Approval.Status.PENDING,
                       Approval.Status.APPROVED):
            Approval.objects.create(
                approval_type=Approval.Type.LEAVE, title='我的单据',
                applicant=self.staff, approver=self.manager, status=status)
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        html = response.content.decode()
        # setUpTestData 里已有 1 条 pending，再补 2 条 → 3
        self.assertEqual(response.context['cards']['mine']['pending'], 3)
        # 注意 'lc-ov-kpis'（容器）是 'lc-ov-kpi'（卡片）的子串，必须连 class 一起数
        self.assertEqual(html.count('class="lc-stat lc-ov-kpi"'), 5)
        self.assertContains(response, '我的待处理')
        self.assertNotContains(response, '待我审批')

    def test_plugin_alert_when_plugin_disabled(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='notice', enabled=False)
        self.client.force_login(self.admin)
        response = self.client.get('/dashboard/')
        self.assertTrue(response.context['cards']['plugins']['alert'])
        self.assertContains(response, '插件未全部启用')

    def test_dashboard_links_drop_with_disabled_plugins(self):
        """v2.1.7：看板卡片上的入口也归启停管——停用插件的链接不能留在页面上。

        卡片正文（统计数字）已经按 enabled_names 收敛，但标题右侧那几个深链
        是写死在模板里的，停用后点了就是 404，等于把入口留在了明面上。
        """
        from plugins.workspace.models import PluginSwitch
        for key in ('approval', 'structure'):
            PluginSwitch.objects.create(app_key=key, enabled=False)
        self.client.force_login(self.admin)
        response = self.client.get('/dashboard/')
        html = response.content.decode()
        self.assertNotIn('/plugins/approval/', html)
        self.assertNotContains(response, '查看组织架构')
        self.assertNotContains(response, '审批中心')
        # 插件卡片本身（管理插件的入口）不受影响
        self.assertEqual(response.status_code, 200)

    def test_chart_disabled_degrades_to_numbers_and_tables(self):
        with override_settings(OA_CHARTS='none'):
            self.client.force_login(self.admin)
            response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'wb-chart-trend')
        self.assertIsNone(response.context['trend']['payload'])
        self.assertContains(response, '单据数')   # 降级表格表头

    def test_admin_pie_and_department_chart(self):
        self.client.force_login(self.admin)
        response = self.client.get('/dashboard/')
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
        self.assertContains(response, 'href="/plugins/notice/" class="ds-rail__row is-active"')

    def test_dashboard_page_has_no_duplicate_rail_entry(self):
        """v2.1.0：看板已搬进首页（`/?panel=dashboard`），业务页侧栏不再重复列一遍。

        深链 `/dashboard/` 仍然保留，只是侧栏不出现这一行——它属于主页那三格。
        """
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/dashboard/"')
        self.assertContains(response, 'class="ds-rail__toggle ds-rail__home"')
        self.assertContains(response, 'aria-label="返回主页"')
        # 业务页不再有折叠开关
        self.assertNotContains(response, 'data-ds-rail-toggle')
        self.assertNotContains(response, 'js/rail-boot.js')

    def test_detail_page_highlights_parent_menu(self):
        approval = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.staff, approver=self.staff)
        self.client.force_login(self.staff)
        response = self.client.get(f'/plugins/approval/{approval.pk}/')
        self.assertContains(response, 'href="/plugins/approval/" class="ds-rail__row is-active"')

    def test_exact_match_wins_over_parent(self):
        manager = User.objects.create_user('mgr', '', 'pw')
        grant(manager, 'attendance_report_view')
        self.client.force_login(manager)
        response = self.client.get('/plugins/attendance/records/')
        self.assertContains(
            response, 'href="/plugins/attendance/records/" class="ds-rail__row is-active"')
        self.assertNotContains(
            response, 'href="/plugins/attendance/" class="ds-rail__row is-active"')
        # v2.1.0：功能页侧栏也不再列「考勤」这一行（它只活在首页第一格）
        self.assertNotContains(response, 'href="/plugins/attendance/"')

