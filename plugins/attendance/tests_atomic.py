"""v1.7.x 考勤打卡并发（防丢更新）测试（新增，不改既有 tests.py）。

覆盖：
- 同一用户同一天两次打卡请求只有一行记录；
- 签退不会清掉并发写入的 check_in（旧实现整行 save 会覆盖）；
- 签到 / 补卡的 status 口径与既有断言一致（迟到 / 缺卡 / 补卡）。
"""

from datetime import datetime, time
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Attendance

User = get_user_model()


class AttendanceAtomicTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Permission

        self.user = User.objects.create_user('atomic_staff', password='pw')
        role = self.user.roles.create(name='打卡岗')
        role.permissions.add(Permission.objects.get(codename='attendance_check'))
        self.day = timezone.localdate()
        self.client.force_login(self.user)

    def _post(self, action, **extra):
        return self.client.post('/plugins/attendance/check/',
                                {'action': action, **extra})

    def _aware(self, clock):
        return timezone.make_aware(datetime.combine(self.day, clock))

    def test_double_check_in_creates_single_row(self):
        self._post('in', sign_type='internal')
        self._post('in', sign_type='internal')
        rows = Attendance.objects.filter(user=self.user, date=self.day)
        self.assertEqual(rows.count(), 1)
        self.assertIsNotNone(rows.first().check_in)

    def test_check_out_keeps_existing_check_in(self):
        self._post('in')
        first = Attendance.objects.get(user=self.user, date=self.day)
        check_in = first.check_in
        self.assertIsNotNone(check_in)

        self._post('out')
        record = Attendance.objects.get(user=self.user, date=self.day)
        self.assertEqual(record.check_in, check_in)      # 签退不清签到
        self.assertIsNotNone(record.check_out)

    def test_concurrent_check_in_not_lost_by_check_out(self):
        """模拟 get_or_create 读到并发前的旧快照：签退只写 check_out。"""
        check_in = self._aware(time(8, 50))
        record = Attendance.objects.create(
            user=self.user, date=self.day, check_in=check_in,
            sign_type=Attendance.SignType.INTERNAL)
        stale = Attendance(pk=record.pk, user=self.user, date=self.day)  # check_in=None

        with mock.patch.object(Attendance.objects, 'get_or_create',
                               return_value=(stale, False)):
            self._post('out')

        self.assertEqual(
            Attendance.objects.filter(user=self.user, date=self.day).count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.check_in, check_in)
        self.assertIsNotNone(record.check_out)

    def test_check_in_status_is_late_after_nine(self):
        with mock.patch('plugins.attendance.views._now',
                        return_value=self._aware(time(9, 30))):
            self._post('in')
        record = Attendance.objects.get(user=self.user, date=self.day)
        self.assertEqual(record.status, Attendance.Status.LATE)

    def test_check_out_status_is_early_before_six(self):
        Attendance.objects.create(
            user=self.user, date=self.day, check_in=self._aware(time(8, 50)))
        with mock.patch('plugins.attendance.views._now',
                        return_value=self._aware(time(17, 0))):
            self._post('out')
        record = Attendance.objects.get(user=self.user, date=self.day)
        self.assertEqual(record.status, Attendance.Status.EARLY)

    def test_makeup_view_keeps_status_and_single_row(self):
        from django.contrib.auth.models import Permission

        manager = User.objects.create_user('atomic_mgr', password='pw')
        role = manager.roles.create(name='补卡管理')
        role.permissions.add(
            Permission.objects.get(codename='attendance_report_view'))
        self.client.force_login(manager)

        Attendance.objects.create(
            user=self.user, date=self.day, check_in=self._aware(time(8, 50)))
        payload = {
            'user': self.user.pk,
            'date': self.day.isoformat(),
            'check_in': '09:00',
            'check_out': '18:00',
            'sign_type': 'external',
        }
        self.client.post('/plugins/attendance/makeup/', payload)
        self.client.post('/plugins/attendance/makeup/', payload)

        rows = Attendance.objects.filter(user=self.user, date=self.day)
        self.assertEqual(rows.count(), 1)
        record = rows.first()
        self.assertTrue(record.is_makeup)
        self.assertEqual(record.status, Attendance.Status.MAKEUP)
        self.assertEqual(record.sign_type, Attendance.SignType.EXTERNAL)
        self.assertEqual(record.check_out, self._aware(time(18, 0)))
