"""attendance 单元测试：一天一卡 / 签到签退 / 迟到统计。"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Attendance

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
