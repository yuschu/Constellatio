"""attendance 插件模型：考勤记录（一天一卡，含签到类型/状态/补卡）+ 考勤规则（单例）。"""

import threading
import time as _monotonic_time
from datetime import date as ddate
from datetime import datetime as dt
from datetime import time as dtime
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# 旧口径（v1.7.1 及之前硬编码的上下班时间）：现仅作为 AttendanceRule 的字段默认值，
# 状态判定一律读 AttendanceRule.get_solo()，不得再直接用这两个常量。
WORK_START = dtime(9, 0)
WORK_END = dtime(18, 0)

# 规则单例行主键固定为 1；进程内缓存 TTL（秒）
RULE_SOLO_PK = 1
RULE_CACHE_TTL = 60

_rule_cache = {'rule': None, 'expires': 0.0}
_rule_cache_lock = threading.Lock()


def _shift(clock, minutes):
    """基准时间 + 分钟数 → 时间（跨零点按 24 小时回绕）。"""
    moment = dt.combine(ddate.min, clock) + timedelta(minutes=minutes)
    return moment.time()


class AttendanceRule(models.Model):
    """考勤规则（单例，pk 固定 1）：上下班时间 / 宽限 / 工作日 / 补卡回溯。

    字段默认值完全复现 v1.7.1 及之前的硬编码口径（09:00 上班、18:00 下班、
    无宽限），因此规则表为空时状态判定结果与旧版一致。
    """

    work_start = models.TimeField('上班时间', default=WORK_START)
    work_end = models.TimeField('下班时间', default=WORK_END)
    late_grace_minutes = models.PositiveSmallIntegerField(
        '迟到宽限（分钟）', default=0)
    early_grace_minutes = models.PositiveSmallIntegerField(
        '早退宽限（分钟）', default=0)
    # ISO 周几（1=周一 … 7=周日），逗号分隔
    workdays = models.CharField('工作日', max_length=20, default='1,2,3,4,5')
    makeup_window_days = models.PositiveSmallIntegerField(
        '补卡回溯天数', default=7)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='最后修改人', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '考勤规则'
        verbose_name_plural = '考勤规则'
        permissions = [
            ('attendance_rule_manage', '考勤规则设置'),
        ]

    @classmethod
    def invalidate_cache(cls):
        """清空进程内规则缓存（save / delete 之后与测试使用）。"""
        with _rule_cache_lock:
            _rule_cache['rule'] = None
            _rule_cache['expires'] = 0.0

    @classmethod
    def get_solo(cls):
        """返回 pk=1 的规则，不存在则用默认值创建；带 60 秒进程内缓存。

        事务内（TestCase / ATOMIC_REQUESTS）直接读 DB：事务回滚后进程缓存
        无法感知，沿用缓存会串测试；事务外才启用 TTL 缓存（与插件开关缓存
        同一策略）。规则每次保存都会让缓存立即失效。
        """
        from django.db import connection

        use_cache = not connection.in_atomic_block
        if use_cache:
            cached = _rule_cache['rule']
            if cached is not None and _monotonic_time.monotonic() < _rule_cache['expires']:
                return cached

        rule, _created = cls.objects.get_or_create(pk=RULE_SOLO_PK)
        if use_cache:
            with _rule_cache_lock:
                _rule_cache['rule'] = rule
                _rule_cache['expires'] = _monotonic_time.monotonic() + RULE_CACHE_TTL
        return rule

    @property
    def workday_set(self):
        """workdays → ISO 周几集合；非法片段忽略（表单已校验）。"""
        days = set()
        for part in (self.workdays or '').split(','):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= 7:
                days.add(int(part))
        return days

    def is_workday(self, day):
        """day（date）是否为本规则的工作日。"""
        return day.isoweekday() in self.workday_set

    def late_threshold(self):
        """迟到判定阈值：work_start + late_grace，签到晚于它即迟到。"""
        return _shift(self.work_start, self.late_grace_minutes)

    def early_threshold(self):
        """早退判定阈值：work_end - early_grace，签退早于它即早退。"""
        return _shift(self.work_end, -self.early_grace_minutes)

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.pk = RULE_SOLO_PK
        super().save(*args, **kwargs)
        self.invalidate_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        self.invalidate_cache()
        return result

    def __str__(self):
        return f'{self.work_start:%H:%M}-{self.work_end:%H:%M}'


class Attendance(models.Model):
    """考勤记录表 attendance_attendance。"""

    class SignType(models.TextChoices):
        INTERNAL = 'internal', '内勤签到'
        EXTERNAL = 'external', '外勤签到'

    class Status(models.TextChoices):
        NORMAL = 'normal', '正常'
        LATE = 'late', '迟到'
        EARLY = 'early', '早退'
        MISSING = 'missing', '缺卡'
        MAKEUP = 'makeup', '补卡'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_records', verbose_name='员工')
    date = models.DateField('日期')
    check_in = models.DateTimeField('上班打卡', null=True, blank=True)
    check_out = models.DateTimeField('下班打卡', null=True, blank=True)
    sign_type = models.CharField(
        '签到类型', max_length=20, choices=SignType.choices, default=SignType.INTERNAL)
    is_makeup = models.BooleanField('是否补卡', default=False)
    status = models.CharField(
        '签到状态', max_length=20, choices=Status.choices, default=Status.MISSING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '考勤记录'
        ordering = ['-date']
        unique_together = ('user', 'date')  # 一天一卡防重复
        # 插件权限码：迁移自动创建为 Permission
        permissions = [
            ('attendance_view', '查看考勤'),
            ('attendance_check', '考勤打卡'),
            # v1.5.4：管理岗查看全员签到详情
            ('attendance_report_view', '查看签到详情'),
        ]

    def compute_status(self):
        """按打卡时间与当前考勤规则推导状态：补卡 > 缺卡 > 迟到 > 早退 > 正常。"""
        if self.is_makeup:
            return self.Status.MAKEUP
        if not self.check_in:
            return self.Status.MISSING
        rule = AttendanceRule.get_solo()
        check_in = timezone.localtime(self.check_in).time()
        if check_in > rule.late_threshold():
            return self.Status.LATE
        if not self.check_out:
            return self.Status.MISSING
        check_out = timezone.localtime(self.check_out).time()
        if check_out < rule.early_threshold():
            return self.Status.EARLY
        return self.Status.NORMAL

    def save(self, *args, **kwargs):
        self.status = self.compute_status()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user_id} {self.date}'
