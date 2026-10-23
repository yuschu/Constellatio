"""v1.5.4 RBAC 准入测试：权限等级 / 全员基线 / 菜单与视图守卫。"""

from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from plugins.attendance.models import Attendance
from plugins.user.models import Role

User = get_user_model()
P = Permission.objects


def _role_with(user, name, *codenames):
    role = Role.objects.create(name=name)
    for codename in codenames:
        role.permissions.add(P.get(codename=codename))
    user.roles.add(role)
    return role


class BaselinePermissionTests(TestCase):
    """全员基线：考勤看板/打卡/公告浏览不依赖角色；管理码仍需授权。"""

    def test_roleless_user_has_baseline_only(self):
        user = User.objects.create_user('staff', password='pw')
        for code in ('attendance_view', 'attendance_check', 'notice_view'):
            self.assertTrue(user.has_perm(code), code)
        self.assertTrue(user.has_perm('attendance.attendance_check'))
        for code in ('attendance_report_view', 'blockchain_view',
                     'structure_view', 'user_manage', 'workspace_manage'):
            self.assertFalse(user.has_perm(code), code)

    def test_frozen_user_loses_baseline(self):
        user = User.objects.create_user('frozen', password='pw', permission_frozen=True)
        self.assertFalse(user.has_perm('attendance_view'))
        self.assertFalse(user.has_perm('notice_view'))

    def test_superuser_has_everything(self):
        root = User.objects.create_superuser('root', '', 'pw')
        self.assertTrue(root.has_perm('attendance_report_view'))
        self.assertTrue(root.has_perm('blockchain_verify'))

    def test_manager_role_grants_report_view(self):
        user = User.objects.create_user('mgr', password='pw')
        _role_with(user, '人力资源经理', 'attendance_report_view')
        self.assertTrue(user.has_perm('attendance_report_view'))
        self.assertEqual(user.level_label, 'L2 管理岗')


class MenuGuardTests(TestCase):
    """菜单可见性 = 视图准入：看得到才进得去。"""

    def test_roleless_menu_has_baseline_plugins_only(self):
        self.client.force_login(User.objects.create_user('staff', password='pw'))
        home = self.client.get('/')
        self.assertContains(home, '考勤打卡')
        self.assertContains(home, '公告中心')
        self.assertNotContains(home, '签到详情')
        self.assertNotContains(home, '审批中心')
        self.assertNotContains(home, '留痕链')
        self.assertNotContains(home, '组织架构')
        self.assertNotContains(home, '插件开关')

    def test_manager_menu_shows_report(self):
        user = User.objects.create_user('mgr', password='pw')
        _role_with(user, '人力资源经理', 'attendance_report_view')
        self.client.force_login(user)
        home = self.client.get('/')
        self.assertContains(home, '签到详情')
        self.assertNotContains(home, '插件开关')


class AttendanceRecordsTests(TestCase):
    """签到详情：管理岗可看全员记录，普通员工 302。"""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('staff', password='pw', last_name='员工甲')
        cls.manager = User.objects.create_user('mgr', password='pw', last_name='经理乙')
        _role_with(cls.manager, 'HR经理', 'attendance_report_view')
        role = Role.objects.create(name='员工')
        role.permissions.add(P.get(codename='approval_view'))
        cls.staff.roles.add(role)
        today = timezone.localdate()
        cls.record = Attendance.objects.create(
            user=cls.staff, date=today,
            check_in=timezone.make_aware(datetime.combine(today, time(9, 30))))

    def test_staff_redirected(self):
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/attendance/records/')
        self.assertEqual(response.status_code, 302)

    def test_manager_sees_all_records(self):
        self.client.force_login(self.manager)
        response = self.client.get('/plugins/attendance/records/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '员工甲')
        self.assertContains(response, '迟到')
        self.assertContains(response, '签到记录')

    def test_manager_filter_by_keyword(self):
        self.client.force_login(self.manager)
        response = self.client.get('/plugins/attendance/records/', {'q': '员工甲'})
        self.assertContains(response, '员工甲')
        response = self.client.get('/plugins/attendance/records/', {'q': '不存在'})
        self.assertContains(response, '当前条件下暂无签到记录')

    def test_staff_can_still_clock_in(self):
        other = User.objects.create_user('other', password='pw')
        self.client.force_login(other)
        response = self.client.post(
            '/plugins/attendance/check/', {'action': 'in'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Attendance.objects.filter(user=other).exists())

    def test_records_page_english(self):
        self.client.force_login(self.manager)
        self.client.cookies['django_language'] = 'en'
        response = self.client.get('/plugins/attendance/records/')
        self.assertContains(response, 'Attendance details')
        self.assertContains(response, 'Late')
        self.assertContains(response, 'Check in')


class PluginViewGuardTests(TestCase):
    """无权限插件视图统一 302 回工作台；有权限 200。"""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('staff', password='pw')
        cls.manager = User.objects.create_user('mgr', password='pw')
        _role_with(cls.manager, '管理岗', 'structure_view', 'blockchain_view',
                   'approval_view', 'attendance_report_view')

    def test_structure_overview_guard(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/plugins/structure/').status_code, 302)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/plugins/structure/').status_code, 200)
        self.assertContains(self.client.get('/plugins/structure/'), '查看模板')

    def test_approval_views_guard(self):
        self.client.force_login(self.staff)
        for url in ('/plugins/approval/', '/plugins/approval/pending/',
                    '/plugins/approval/new/'):
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/plugins/approval/').status_code, 200)

    def test_blockchain_guard(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/plugins/blockchain/').status_code, 302)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/plugins/blockchain/').status_code, 200)

    def test_apply_structure_requires_manage(self):
        self.client.force_login(self.manager)      # 仅 structure_view
        self.assertEqual(
            self.client.post('/plugins/structure/apply/').status_code, 302)
