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
