"""notice 插件模型：公告 + 已读记录。"""

from django.conf import settings
from django.db import models


class Announcement(models.Model):
    """公告表 notice_announcement。"""

    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容')
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='announcements', verbose_name='发布人')
    is_top = models.BooleanField('置顶', default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '公告'
        ordering = ['-is_top', '-created_at']
        # 插件权限码：迁移自动创建为 Permission
        permissions = [
            ('notice_view', '查看公告'),
            ('notice_manage', '发布公告'),
        ]

    def __str__(self):
        return self.title


class AnnouncementRead(models.Model):
    """公告已读表 notice_announcementread（一人一篇只记一次）。"""

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE,
        related_name='read_records', verbose_name='公告')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='announcement_reads', verbose_name='读者')
    read_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '公告已读'
        unique_together = ('announcement', 'user')

    def __str__(self):
        return f'{self.announcement_id}-{self.user_id}'
