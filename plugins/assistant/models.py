"""assistant 插件模型：对话与消息（v2.3.0 A 阶段）。

只保存对话文本与工具调用参数，不保存模型原文、不保存思维链。
"""

from django.conf import settings
from django.db import models

from plugin_host.models import AuditModel


class Conversation(AuditModel):
    """一次对话（按用户隔离）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='assistant_conversations', verbose_name='用户')
    title = models.CharField('标题', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '助手对话'
        verbose_name_plural = '助手对话'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
        ]

    def __str__(self):
        return self.title or f'#{self.pk}'


class Message(AuditModel):
    """对话中的一条消息。role=tool 时 content 为工具结果 JSON。"""

    class Role(models.TextChoices):
        USER = 'user', '用户'
        ASSISTANT = 'assistant', '助手'
        TOOL = 'tool', '工具'

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE,
        related_name='messages', verbose_name='对话')
    role = models.CharField('角色', max_length=20, choices=Role.choices)
    content = models.TextField('内容', blank=True, default='')
    tool_calls = models.JSONField('工具调用', default=list, blank=True)
    tool_call_id = models.CharField('工具调用 ID', max_length=100, blank=True, default='')
    tokens_in = models.PositiveIntegerField('输入 token', default=0)
    tokens_out = models.PositiveIntegerField('输出 token', default=0)

    class Meta:
        verbose_name = '助手消息'
        verbose_name_plural = '助手消息'
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.conversation_id} {self.role} {self.content[:20]}'
