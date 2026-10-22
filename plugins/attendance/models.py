"""attendance 插件模型：考勤记录（一天一卡，含签到类型/状态/补卡）。"""

from datetime import time as dtime

from django.conf import settings
from django.db import models
from django.utils import timezone

# 考勤口径：09:00 上班、18:00 下班（迟到 / 早退判定）
WORK_START = dtime(9, 0)
WORK_END = dtime(18, 0)


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
        """按打卡时间推导状态：补卡 > 缺卡 > 迟到 > 早退 > 正常。"""
        if self.is_makeup:
            return self.Status.MAKEUP
        if not self.check_in:
            return self.Status.MISSING
        check_in = timezone.localtime(self.check_in).time()
        if check_in > WORK_START:
            return self.Status.LATE
        if not self.check_out:
            return self.Status.MISSING
        check_out = timezone.localtime(self.check_out).time()
        if check_out < WORK_END:
            return self.Status.EARLY
        return self.Status.NORMAL

    def save(self, *args, **kwargs):
        self.status = self.compute_status()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user_id} {self.date}'
