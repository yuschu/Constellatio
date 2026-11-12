"""v1.7.14：attendance 插件 service 层单测（状态判定 / 打卡 / 补卡，零 request）。

判据验证点：
- `judge_status` 传入 `rule` 时完全不碰数据库 —— 用 `assertNumQueries(0)` 证明；
- `check` / `register_makeup` 的行锁与 `update_fields` 语义（重复打卡只落一行、
  签退不清掉签到时间）直接调 service 验证，不经过视图。
"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from . import services
from .models import Attendance, AttendanceRule

User = get_user_model()


def _aware(day, clock):
    return timezone.make_aware(datetime.combine(day, clock))


class JudgeStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.day = timezone.localdate()
        cls.rule = AttendanceRule.get_solo()

    def test_makeup_wins_over_everything(self):
        status = services.judge_status(
            is_makeup=True, check_in=_aware(self.day, time(23, 59)),
            check_out=_aware(self.day, time(0, 1)), rule=self.rule)
        self.assertEqual(status, Attendance.Status.MAKEUP)

    def test_missing_when_no_check_in(self):
        self.assertEqual(
            services.judge_status(is_makeup=False, check_in=None, check_out=None, rule=self.rule),
            Attendance.Status.MISSING)

    def test_late_when_check_in_after_threshold(self):
        late = self.rule.late_threshold()
        clock = time(late.hour, late.minute + 1, 0)
        self.assertEqual(
            services.judge_status(
                is_makeup=False, check_in=_aware(self.day, clock),
                check_out=_aware(self.day, time(18, 0)), rule=self.rule),
            Attendance.Status.LATE)

    def test_early_when_check_out_before_threshold(self):
        early = self.rule.early_threshold()
        clock = time(early.hour - 1, 0, 0)
        self.assertEqual(
            services.judge_status(
                is_makeup=False, check_in=_aware(self.day, self.rule.work_start),
                check_out=_aware(self.day, clock), rule=self.rule),
            Attendance.Status.EARLY)

    def test_normal_and_zero_queries(self):
        """传入 rule 时判定是纯函数：不查库。"""
        with self.assertNumQueries(0):
            status = services.judge_status(
                is_makeup=False, check_in=_aware(self.day, self.rule.work_start),
                check_out=_aware(self.day, self.rule.work_end), rule=self.rule)
        self.assertEqual(status, Attendance.Status.NORMAL)


class CheckAndMakeupServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('svc_emp', password='pw')
        cls.manager = User.objects.create_user('svc_mgr', password='pw')
        cls.day = timezone.localdate()

    def test_check_in_then_out_single_row(self):
        """重复打卡只落同一行：先 in 再 in 不会新增记录，check_in 不被覆盖。"""
        services.check(self.user, action='in', now=_aware(self.day, time(8, 55)))
        first = Attendance.objects.get(user=self.user, date=self.day)
        services.check(self.user, action='in', now=_aware(self.day, time(9, 30)))
        services.check(self.user, action='out', now=_aware(self.day, time(18, 5)))

        self.assertEqual(Attendance.objects.filter(user=self.user, date=self.day).count(), 1)
        record = Attendance.objects.get(user=self.user, date=self.day)
        self.assertEqual(record.check_in, first.check_in)      # 第二次 in 被忽略
        self.assertIsNotNone(record.check_out)
        self.assertEqual(record.status, Attendance.Status.NORMAL)

    def test_check_out_does_not_clear_concurrent_check_in(self):
        """锁内只写本次改动字段：已存在 check_in 时签退不覆盖它。"""
        check_in = _aware(self.day, time(8, 50))
        Attendance.objects.create(user=self.user, date=self.day, check_in=check_in)
        services.check(self.user, action='out', now=_aware(self.day, time(17, 30)))
        record = Attendance.objects.get(user=self.user, date=self.day)
        self.assertEqual(record.check_in, check_in)
        self.assertEqual(record.status, Attendance.Status.EARLY)

    def test_register_makeup_marks_status_and_type(self):
        target = User.objects.create_user('svc_makeup_target', password='pw')
        record = services.register_makeup(
            self.manager, target, self.day, sign_type=Attendance.SignType.EXTERNAL,
            check_in=_aware(self.day, time(9, 0)), check_out=_aware(self.day, time(18, 0)))
        self.assertTrue(record.is_makeup)
        self.assertEqual(record.status, Attendance.Status.MAKEUP)
        self.assertEqual(record.sign_type, Attendance.SignType.EXTERNAL)

    def test_register_makeup_logs_operator(self):
        """`operator` 不是死参数：补卡要留一条「谁替谁登记」的日志（审计列只记写入人）。"""
        target = User.objects.create_user('svc_makeup_target3', password='pw')
        with self.assertLogs('plugins.attendance.services', level='INFO') as captured:
            services.register_makeup(self.manager, target, self.day,
                                     check_in=_aware(self.day, time(9, 0)))
        joined = '\n'.join(captured.output)
        self.assertIn(f'operator={self.manager.pk}', joined)
        self.assertIn(f'target={target.pk}', joined)

    def test_register_makeup_keeps_single_row_per_day(self):
        target = User.objects.create_user('svc_makeup_target2', password='pw')
        services.register_makeup(self.manager, target, self.day,
                                 check_in=_aware(self.day, time(9, 0)))
        services.register_makeup(self.manager, target, self.day,
                                 check_in=_aware(self.day, time(10, 0)))
        self.assertEqual(Attendance.objects.filter(user=target, date=self.day).count(), 1)
        self.assertEqual(
            Attendance.objects.get(user=target, date=self.day).check_in,
            _aware(self.day, time(10, 0)))


class RuleThresholdTests(TestCase):
    """阈值边界（补卡窗口 / 迟到阈值）走 service 可见的规则对象，证明判定可脱离视图。"""

    def test_late_threshold_includes_grace(self):
        """阈值 = 上班时间 + 宽限分钟（跨小时也要对，所以用 datetime 运算而不是拼 hour/minute）。"""
        rule = AttendanceRule.get_solo()
        expected = (datetime.combine(date.today(), rule.work_start)
                    + timedelta(minutes=rule.late_grace_minutes)).time()
        self.assertEqual(rule.late_threshold(), expected)

    def test_status_field_of_new_record_uses_service(self):
        """模型 save() 仍按 service 口径重算（防止有人把判定写回模型）。"""
        user = User.objects.create_user('svc_status_user', password='pw')
        day = date.today()
        record = Attendance.objects.create(
            user=user, date=day, check_in=_aware(day, time(23, 0)))
        self.assertEqual(record.status, Attendance.Status.LATE)
