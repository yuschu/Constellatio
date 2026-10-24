"""notify 插件模型：站内信（审批待办 / 审批结果 / 公告）。"""

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """站内消息表 notify_notification。"""

    class Category(models.TextChoices):
        APPROVAL = 'approval', '审批'
        NOTICE = 'notice', '公告'
        SYSTEM = 'system', '系统'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications', verbose_name='接收人')
    category = models.CharField(
        '类别', max_length=20, choices=Category.choices, default=Category.SYSTEM)
    title = models.CharField('标题', max_length=200)
    body = models.TextField('正文', blank=True)
    link = models.CharField('跳转链接', max_length=300, blank=True)
    is_read = models.BooleanField('已读', default=False)
    read_at = models.DateTimeField('已读时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '站内消息'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'is_read'])]
        permissions = [('notify_view', '查看消息')]

    def __str__(self):
        return f'{self.recipient_id}:{self.title}'
