"""attendance 插件模型：考勤记录（一天一卡）。"""

from django.conf import settings
from django.db import models


class Attendance(models.Model):
    """考勤记录表 attendance_attendance。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_records', verbose_name='员工')
    date = models.DateField('日期')
    check_in = models.DateTimeField('上班打卡', null=True, blank=True)
    check_out = models.DateTimeField('下班打卡', null=True, blank=True)
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

    def __str__(self):
        return f'{self.user_id} {self.date}'
