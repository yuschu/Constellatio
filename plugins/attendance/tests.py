"""attendance 单元测试：一天一卡 / 签到签退 / 迟到统计 / 考勤规则（v1.7.2）。"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .forms import AttendanceRuleForm
from .models import Attendance, AttendanceRule

User = get_user_model()


class AttendanceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff', password='pw')

    def _record(self, date, check_in=None, check_out=None):
        return Attendance.objects.create(
            user=self.user, date=date, check_in=check_in, check_out=check_out)

    def test_one_card_per_day(self):
        day = timezone.localdate()
        a1 = Attendance.objects.create(user=self.user, date=day)
        # 同一天再次打卡应复用同一记录（unique_together 由 get_or_create 保证）
        a2, created = Attendance.objects.get_or_create(user=self.user, date=day)
        self.assertFalse(created)
        self.assertEqual(a1.id, a2.id)

    def test_check_in_out(self):
        day = timezone.localdate()
        a = Attendance.objects.create(user=self.user, date=day)
        a.check_in = timezone.make_aware(datetime.combine(day, time(8, 50)))
        a.check_out = timezone.make_aware(datetime.combine(day, time(18, 10)))
        a.save()
        a.refresh_from_db()
        self.assertEqual(timezone.localtime(a.check_in).hour, 8)
        self.assertEqual(timezone.localtime(a.check_out).hour, 18)

    def test_late_count(self):
        today = timezone.localdate()
        self._record(today, check_in=timezone.make_aware(datetime.combine(today, time(8, 50))))          # 正常
        self._record(today - timedelta(days=1),
                     check_in=timezone.make_aware(datetime.combine(today - timedelta(days=1), time(9, 5))))  # 迟到
        month_start = today.replace(day=1)
        late = Attendance.objects.filter(
            user=self.user, date__gte=month_start,
            check_in__time__gt=time(9, 0)).count()
        self.assertEqual(late, 1)


class AttendanceStatusTests(TestCase):
    """v1.5.5：状态推导与签到类型。"""

    def setUp(self):
        self.user = User.objects.create_user('staff', password='pw')
        self.day = timezone.localdate()

    def _make(self, check_in=None, check_out=None, **kwargs):
        record = Attendance.objects.create(user=self.user, date=self.day, **kwargs)
        if check_in:
            record.check_in = timezone.make_aware(datetime.combine(self.day, check_in))
        if check_out:
            record.check_out = timezone.make_aware(datetime.combine(self.day, check_out))
        record.save()
        return record

    def test_status_normal(self):
        record = self._make(time(8, 50), time(18, 10))
        self.assertEqual(record.status, Attendance.Status.NORMAL)

    def test_status_late(self):
        record = self._make(time(9, 30), time(18, 10))
        self.assertEqual(record.status, Attendance.Status.LATE)

    def test_status_early(self):
        record = self._make(time(8, 50), time(17, 0))
        self.assertEqual(record.status, Attendance.Status.EARLY)

    def test_status_missing(self):
        self.assertEqual(self._make(time(9, 0), None).status, Attendance.Status.MISSING)
        self.day = self.day - timedelta(days=1)
        self.assertEqual(self._make().status, Attendance.Status.MISSING)

    def test_status_makeup(self):
        record = self._make(time(9, 0), time(18, 0), is_makeup=True)
        self.assertEqual(record.status, Attendance.Status.MAKEUP)

    def test_check_stores_sign_type(self):
        self.client.force_login(self.user)
        self.client.post('/plugins/attendance/check/',
                         {'action': 'in', 'sign_type': 'external'})
        record = Attendance.objects.get(user=self.user, date=self.day)
        self.assertEqual(record.sign_type, Attendance.SignType.EXTERNAL)


class AttendanceRecordFilterTests(TestCase):
    """v1.5.5：签到详情筛选（时间范围 / 状态 / 类型）。"""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission

        from plugins.user.models import Role
        cls.day = timezone.localdate()
        cls.manager = User.objects.create_user('mgr', password='pw')
        role = Role.objects.create(name='考勤管理')
        role.permissions.add(Permission.objects.get(codename='attendance_report_view'))
        cls.manager.roles.add(role)
        cls.late_user = User.objects.create_user('late', password='pw', last_name='迟到者')
        cls.early_user = User.objects.create_user('early', password='pw', last_name='早退者')
        cls.late_record = Attendance.objects.create(
            user=cls.late_user, date=cls.day, sign_type=Attendance.SignType.INTERNAL,
            check_in=timezone.make_aware(datetime.combine(cls.day, time(9, 30))),
            check_out=timezone.make_aware(datetime.combine(cls.day, time(18, 10))))
        cls.early_record = Attendance.objects.create(
            user=cls.early_user, date=cls.day, sign_type=Attendance.SignType.EXTERNAL,
            check_in=timezone.make_aware(datetime.combine(cls.day, time(8, 50))),
            check_out=timezone.make_aware(datetime.combine(cls.day, time(17, 0))))

    def setUp(self):
        self.client.force_login(self.manager)

    def test_filter_status(self):
        response = self.client.get('/plugins/attendance/records/', {'status': 'late'})
        self.assertContains(response, '<td>迟到者</td>')
        self.assertNotContains(response, '<td>早退者</td>')
        response = self.client.get('/plugins/attendance/records/', {'status': 'early'})
        self.assertContains(response, '<td>早退者</td>')
        self.assertNotContains(response, '<td>迟到者</td>')

    def test_filter_sign_type(self):
        response = self.client.get('/plugins/attendance/records/', {'sign_type': 'external'})
        self.assertContains(response, '<td>早退者</td>')
        self.assertNotContains(response, '<td>迟到者</td>')

    def test_filter_time_range(self):
        start = datetime.combine(self.day, time(9, 15)).strftime('%Y-%m-%dT%H:%M')
        end = datetime.combine(self.day, time(10, 0)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.get('/plugins/attendance/records/',
                                   {'start': start, 'end': end})
        self.assertContains(response, '<td>迟到者</td>')
        self.assertNotContains(response, '<td>早退者</td>')

    def test_makeup_marks_status(self):
        self.client.post('/plugins/attendance/makeup/', {
            'user': self.early_user.pk,
            'date': self.day.isoformat(),
            'check_in': '09:00',
            'check_out': '18:00',
            'sign_type': 'internal',
        })
        self.early_record.refresh_from_db()
        self.assertTrue(self.early_record.is_makeup)
        self.assertEqual(self.early_record.status, Attendance.Status.MAKEUP)
        self.assertEqual(self.early_record.sign_type, Attendance.SignType.INTERNAL)
        response = self.client.get('/plugins/attendance/records/', {'status': 'makeup'})
        self.assertContains(response, '早退者')

    def test_makeup_requires_report_perm(self):
        staff = User.objects.create_user('plain', password='pw')
        self.client.force_login(staff)
        response = self.client.post('/plugins/attendance/makeup/', {
            'user': self.late_user.pk, 'date': self.day.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.late_record.refresh_from_db()
        self.assertFalse(self.late_record.is_makeup)


class AttendanceStatsTests(TestCase):
    """v1.6：月度统计 JSON（图表数据源）与权限 / 口径 / 降级。"""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission

        from plugins.user.models import Department, Role

        cls.manager = User.objects.create_user('statsmgr', password='pw')
        role = Role.objects.create(name='统计管理')
        role.permissions.add(Permission.objects.get(codename='attendance_report_view'))
        cls.manager.roles.add(role)
        cls.staff = User.objects.create_user('statsstaff', password='pw')

        cls.today = timezone.localdate()
        cls.first = cls.today.replace(day=1)
        cls.department = Department.objects.create(name='统计财务部')
        cls.late_user = User.objects.create_user(
            'late1', password='pw', last_name='迟到甲', department=cls.department)
        cls.normal_user = User.objects.create_user(
            'normal1', password='pw', last_name='正常乙')
        cls.late_record = Attendance.objects.create(
            user=cls.late_user, date=cls.first,
            check_in=timezone.make_aware(datetime.combine(cls.first, time(9, 30))),
            check_out=timezone.make_aware(datetime.combine(cls.first, time(18, 10))))
        cls.normal_record = Attendance.objects.create(
            user=cls.normal_user, date=cls.first,
            check_in=timezone.make_aware(datetime.combine(cls.first, time(8, 50))),
            check_out=timezone.make_aware(datetime.combine(cls.first, time(18, 5))))

    def setUp(self):
        self.client.force_login(self.manager)

    def _get(self, **params):
        return self.client.get('/plugins/attendance/stats/', params)

    def test_requires_report_perm(self):
        self.client.force_login(self.staff)
        response = self._get()
        self.assertEqual(response.status_code, 302)

    def test_defaults_to_current_month(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['month'], self.today.strftime('%Y-%m'))
        self.assertEqual(len(data['dates']), len(_month_days_for(self.first)))
        self.assertEqual([item['key'] for item in data['series']],
                         [status.value for status in Attendance.Status])

    def test_aggregates_match_records(self):
        data = self._get(month=self.first.strftime('%Y-%m')).json()
        series = {item['key']: item for item in data['series']}
        # 本月第 1 天：1 条迟到 + 1 条正常
        self.assertEqual(series['normal']['data'][0], 1)
        self.assertEqual(series['late']['data'][0], 1)
        self.assertEqual(series['early']['data'][0], 0)
        self.assertEqual(data['totals']['records'], 2)
        self.assertEqual(data['totals']['late'], 1)
        self.assertEqual({user['username'] for user in data['users']},
                         {'late1', 'normal1'})
        self.assertEqual(data['range']['start'], self.first.isoformat())

    def test_department_filter(self):
        data = self._get(
            month=self.first.strftime('%Y-%m'), department=self.department.pk).json()
        self.assertEqual(data['totals']['records'], 1)
        self.assertEqual([user['username'] for user in data['users']], ['late1'])

    def test_invalid_month_returns_400(self):
        response = self._get(month='2026-13')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_month')

    def test_payload_uses_active_chart(self):
        data = self._get(month=self.first.strftime('%Y-%m')).json()
        self.assertEqual(data['payload']['engine'], 'echarts')
        self.assertEqual(data['payload']['option']['xAxis']['data'], data['dates'])

    @override_settings(OA_CHARTS='')
    def test_payload_none_when_chart_disabled(self):
        data = self._get(month=self.first.strftime('%Y-%m')).json()
        self.assertIsNone(data['payload'])
        # 停用只影响图表，数据仍可查询
        self.assertEqual(data['totals']['records'], 2)


class AttendanceChartPageTests(TestCase):
    """v1.6：签到详情月度看板与停用降级表格。"""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission

        from plugins.user.models import Role

        cls.manager = User.objects.create_user('chartmgr', password='pw')
        role = Role.objects.create(name='看板管理')
        role.permissions.add(Permission.objects.get(codename='attendance_report_view'))
        cls.manager.roles.add(role)
        cls.today = timezone.localdate()
        cls.first = cls.today.replace(day=1)
        Attendance.objects.create(
            user=cls.manager, date=cls.first,
            check_in=timezone.make_aware(datetime.combine(cls.first, time(8, 50))),
            check_out=timezone.make_aware(datetime.combine(cls.first, time(18, 5))))

    def setUp(self):
        self.client.force_login(self.manager)

    def test_records_page_renders_chart(self):
        response = self.client.get('/plugins/attendance/records/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '月度看板')
        self.assertContains(response, 'attendance-chart')
        self.assertContains(response, 'vendor/echarts.min.js')
        self.assertContains(response, 'js/echarts.js')
        self.assertContains(response, 'oaChartRender')

    @override_settings(OA_CHARTS='none')
    def test_records_page_degrades_without_chart(self):
        response = self.client.get('/plugins/attendance/records/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '月度看板')
        self.assertContains(response, 'attendance-chart-fallback')
        self.assertNotContains(response, 'vendor/echarts.min.js')
        self.assertNotContains(response, 'oaChartRender')

    def test_month_param_controls_board(self):
        previous = (self.first - timedelta(days=1)).replace(day=1)
        month_value = previous.strftime('%Y-%m')
        response = self.client.get('/plugins/attendance/records/', {'month': month_value})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{month_value}"')
        self.assertContains(response, '本月暂无考勤记录')

    def test_db_chart_switch_degrades(self):
        """v1.6.1：workspace 运行时开关关闭图表引擎 → 页面表格、stats payload=null。"""
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='charts', enabled=False)

        response = self.client.get('/plugins/attendance/records/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'vendor/echarts.min.js')
        stats = self.client.get('/plugins/attendance/stats/').json()
        self.assertIsNone(stats['payload'])
        self.assertEqual(stats['totals']['records'], 1)


def _month_days_for(first):
    """测试辅助：与视图同口径的当月天数列表。"""
    import calendar
    from datetime import timedelta
    last_day = calendar.monthrange(first.year, first.month)[1]
    return [first + timedelta(days=offset) for offset in range(last_day)]



# ---------------------------------------------------------------------------
# v1.7.2：考勤规则（AttendanceRule）——状态判定来源可配置
# ---------------------------------------------------------------------------

class AttendanceRuleStatusTests(TestCase):
    """状态判定改读 AttendanceRule：默认口径不变，改规则后按新口径判定。"""

    def setUp(self):
        self.user = User.objects.create_user('rulestaff', password='pw')
        self.day = timezone.localdate()

    def _save_rule(self, **fields):
        rule = AttendanceRule.get_solo()
        for key, value in fields.items():
            setattr(rule, key, value)
        rule.save()
        return rule

    def _status(self, offset, check_in=None, check_out=None, is_makeup=False):
        day = self.day - timedelta(days=offset)
        record = Attendance.objects.create(
            user=self.user, date=day, is_makeup=is_makeup)
        if check_in:
            record.check_in = timezone.make_aware(datetime.combine(day, check_in))
        if check_out:
            record.check_out = timezone.make_aware(datetime.combine(day, check_out))
        record.save()
        record.refresh_from_db()
        return record.status

    def test_default_rule_values(self):
        rule = AttendanceRule.get_solo()
        self.assertEqual(rule.pk, 1)
        self.assertEqual(rule.work_start, time(9, 0))
        self.assertEqual(rule.work_end, time(18, 0))
        self.assertEqual(rule.late_grace_minutes, 0)
        self.assertEqual(rule.early_grace_minutes, 0)
        self.assertEqual(rule.workdays, '1,2,3,4,5')
        self.assertEqual(rule.makeup_window_days, 7)

    def test_default_status_unchanged(self):
        """默认 09:00/18:00 下，既有迟到 / 早退 / 正常 / 缺卡口径完全不变。"""
        self.assertEqual(self._status(0, time(8, 50), time(18, 10)),
                         Attendance.Status.NORMAL)
        self.assertEqual(self._status(1, time(9, 0), time(18, 0)),
                         Attendance.Status.NORMAL)
        self.assertEqual(self._status(2, time(9, 30), time(18, 10)),
                         Attendance.Status.LATE)
        self.assertEqual(self._status(3, time(8, 50), time(17, 0)),
                         Attendance.Status.EARLY)
        self.assertEqual(self._status(4, time(9, 0), None),
                         Attendance.Status.MISSING)
        self.assertEqual(self._status(5, None, None), Attendance.Status.MISSING)
        self.assertEqual(self._status(6, time(9, 30), time(17, 0), is_makeup=True),
                         Attendance.Status.MAKEUP)

    def test_work_start_change_makes_0930_normal(self):
        """上班时间改为 10:00 后，09:30 打卡为正常（旧口径会是迟到）。"""
        self._save_rule(work_start=time(10, 0))
        self.assertEqual(self._status(0, time(9, 30), time(18, 10)),
                         Attendance.Status.NORMAL)
        self.assertEqual(self._status(1, time(10, 30), time(18, 10)),
                         Attendance.Status.LATE)

    def test_late_grace_minutes(self):
        """迟到宽限 15 分钟：09:10 正常，09:20 仍迟到。"""
        self._save_rule(late_grace_minutes=15)
        self.assertEqual(self._status(0, time(9, 10), time(18, 10)),
                         Attendance.Status.NORMAL)
        self.assertEqual(self._status(1, time(9, 20), time(18, 10)),
                         Attendance.Status.LATE)

    def test_early_grace_minutes(self):
        """早退宽限 15 分钟：17:50 正常，17:40 仍早退。"""
        self._save_rule(early_grace_minutes=15)
        self.assertEqual(self._status(0, time(8, 50), time(17, 50)),
                         Attendance.Status.NORMAL)
        self.assertEqual(self._status(1, time(8, 50), time(17, 40)),
                         Attendance.Status.EARLY)

    def test_thresholds(self):
        rule = self._save_rule(
            late_grace_minutes=10, early_grace_minutes=20)
        self.assertEqual(rule.late_threshold(), time(9, 10))
        self.assertEqual(rule.early_threshold(), time(17, 40))


class AttendanceRuleWorkdayTests(TestCase):
    """workdays 解析与 is_workday。"""

    def test_workday_set_default(self):
        rule = AttendanceRule.get_solo()
        self.assertEqual(rule.workday_set, {1, 2, 3, 4, 5})

    def test_workday_set_parses_and_ignores_noise(self):
        rule = AttendanceRule(workdays='7, 1,6')
        self.assertEqual(rule.workday_set, {1, 6, 7})

    def test_is_workday(self):
        rule = AttendanceRule.get_solo()
        self.assertTrue(rule.is_workday(date(2024, 1, 1)))    # 周一
        self.assertFalse(rule.is_workday(date(2024, 1, 7)))   # 周日


class AttendanceRulePermissionTests(TestCase):
    """规则页权限：无权限 GET 302 / POST 被拒；有权限可保存落库。"""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission

        from plugins.user.models import Role

        cls.day = timezone.localdate()
        cls.staff = User.objects.create_user('rulestaff2', password='pw')
        cls.manager = User.objects.create_user('rulemanager', password='pw')
        role = Role.objects.create(name='考勤规则管理员')
        role.permissions.add(
            Permission.objects.get(codename='attendance_rule_manage'))
        cls.manager.roles.add(role)

    def _payload(self, **overrides):
        data = {
            'work_start': '09:00',
            'work_end': '18:00',
            'late_grace_minutes': '0',
            'early_grace_minutes': '0',
            'workdays': '1,2,3,4,5',
            'makeup_window_days': '7',
        }
        data.update(overrides)
        return data

    def test_staff_get_redirected(self):
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/attendance/rules/')
        self.assertEqual(response.status_code, 302)

    def test_staff_post_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            '/plugins/attendance/rules/', self._payload(work_start='10:00'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AttendanceRule.objects.filter(pk=1).exists())

    def test_manager_get_renders_form(self):
        self.client.force_login(self.manager)
        response = self.client.get('/plugins/attendance/rules/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '考勤规则')

    def test_manager_post_saves(self):
        self.client.force_login(self.manager)
        response = self.client.post('/plugins/attendance/rules/', self._payload(
            work_start='10:00', work_end='19:00', late_grace_minutes='15',
            early_grace_minutes='10', workdays='1,2,3,4,5,6',
            makeup_window_days='30'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/plugins/attendance/rules/', response['Location'])
        rule = AttendanceRule.objects.get(pk=1)
        self.assertEqual(rule.work_start, time(10, 0))
        self.assertEqual(rule.work_end, time(19, 0))
        self.assertEqual(rule.late_grace_minutes, 15)
        self.assertEqual(rule.early_grace_minutes, 10)
        self.assertEqual(rule.workdays, '1,2,3,4,5,6')
        self.assertEqual(rule.makeup_window_days, 30)
        self.assertEqual(rule.updated_by, self.manager)

    def test_manager_invalid_post_keeps_old_rule(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            '/plugins/attendance/rules/', self._payload(work_start='19:00'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceRule.get_solo().work_start, time(9, 0))


class AttendanceRuleFormTests(TestCase):
    """表单校验：上下班先后 / 宽限范围 / 工作日取值 / 补卡回溯范围。"""

    def _data(self, **overrides):
        data = {
            'work_start': '09:00',
            'work_end': '18:00',
            'late_grace_minutes': '0',
            'early_grace_minutes': '0',
            'workdays': '1,2,3,4,5',
            'makeup_window_days': '7',
        }
        data.update(overrides)
        return data

    def test_valid_sorts_and_dedupes_workdays(self):
        form = AttendanceRuleForm(data=self._data(workdays='5,1,1,3'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['workdays'], '1,3,5')

    def test_work_start_not_before_work_end(self):
        form = AttendanceRuleForm(data=self._data(work_start='18:00', work_end='09:00'))
        self.assertFalse(form.is_valid())
        self.assertIn('work_end', form.errors)

    def test_grace_out_of_range(self):
        self.assertFalse(AttendanceRuleForm(
            data=self._data(late_grace_minutes='121')).is_valid())
        self.assertFalse(AttendanceRuleForm(
            data=self._data(early_grace_minutes='121')).is_valid())

    def test_workdays_out_of_range(self):
        form = AttendanceRuleForm(data=self._data(workdays='1,2,8'))
        self.assertFalse(form.is_valid())
        self.assertIn('workdays', form.errors)

    def test_workdays_non_numeric(self):
        form = AttendanceRuleForm(data=self._data(workdays='mon'))
        self.assertFalse(form.is_valid())
        self.assertIn('workdays', form.errors)

    def test_makeup_window_out_of_range(self):
        self.assertFalse(AttendanceRuleForm(
            data=self._data(makeup_window_days='0')).is_valid())
        self.assertFalse(AttendanceRuleForm(
            data=self._data(makeup_window_days='91')).is_valid())


class AttendanceRuleCacheTests(TransactionTestCase):
    """规则进程内缓存：save() 后立即失效，下一次 get_solo 读到新值。

    用 TransactionTestCase（非 atomic）才能真正走到 TTL 缓存分支：
    TestCase 内的 atomic 事务会绕过缓存（与插件开关缓存同一策略）。
    """

    def setUp(self):
        AttendanceRule.invalidate_cache()
        self.addCleanup(AttendanceRule.invalidate_cache)

    def test_save_invalidates_solo_cache(self):
        rule = AttendanceRule.get_solo()
        self.assertEqual(rule.work_start, time(9, 0))
        # 缓存命中：TTL 内返回同一实例（不再查库）
        self.assertIs(AttendanceRule.get_solo(), rule)

        rule.work_start = time(10, 0)
        rule.save()

        self.assertEqual(AttendanceRule.get_solo().work_start, time(10, 0))

    def test_invalid_post_does_not_pollute_cache(self):
        """非法 POST 不能让 get_solo() 缓存的规则对象被表单原地写脏。"""
        from django.contrib.auth.models import Permission

        from plugins.user.models import Role

        manager = User.objects.create_user('cachemgr', password='pw')
        role = Role.objects.create(name='缓存口径管理')
        role.permissions.add(
            Permission.objects.get(codename='attendance_rule_manage'))
        manager.roles.add(role)

        warm = AttendanceRule.get_solo()
        self.client.force_login(manager)
        response = self.client.post('/plugins/attendance/rules/', {
            'work_start': '19:00',
            'work_end': '18:00',
            'late_grace_minutes': '0',
            'early_grace_minutes': '0',
            'workdays': '1,2,3,4,5',
            'makeup_window_days': '7',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIs(AttendanceRule.get_solo(), warm)
        self.assertEqual(AttendanceRule.get_solo().work_start, time(9, 0))


class AttendanceRuleEntryTests(TestCase):
    """入口与看板展示：规则按钮按权限渲染，今日状态卡展示当前口径。"""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission

        from plugins.user.models import Role

        cls.staff = User.objects.create_user('entrystaff', password='pw')
        cls.manager = User.objects.create_user('entrymanager', password='pw')
        role = Role.objects.create(name='口径管理')
        role.permissions.add(
            Permission.objects.get(codename='attendance_rule_manage'))
        cls.manager.roles.add(role)

    def test_dashboard_shows_rule_summary(self):
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/attendance/')
        self.assertContains(response, '上班 09:00 · 下班 18:00')

    def test_dashboard_rule_button_requires_perm(self):
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/attendance/')
        self.assertNotContains(response, 'rules/')

        self.client.force_login(self.manager)
        response = self.client.get('/plugins/attendance/')
        self.assertContains(response, '/plugins/attendance/rules/')
