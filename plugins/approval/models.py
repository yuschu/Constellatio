"""approval 插件模型：审批单 + 流转记录（状态机 draft→pending→approved/rejected）。"""

from django.conf import settings
from django.db import models


class Approval(models.Model):
    """审批单表 approval_approval。"""

    class Type(models.TextChoices):
        LEAVE = 'leave', '请假'
        EXPENSE = 'expense', '报销'
        SEAL = 'seal', '用章'

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING = 'pending', '待审批'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已驳回'

    approval_type = models.CharField('审批类型', max_length=20, choices=Type.choices)
    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容', blank=True)
    amount = models.DecimalField('金额', max_digits=12, decimal_places=2, null=True, blank=True)
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='approvals', verbose_name='申请人')
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='approval_tasks', verbose_name='审批人')
    status = models.CharField(
        '状态', max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '审批单'
        ordering = ['-created_at']
        # 插件权限码：迁移自动创建为 Permission
        permissions = [
            ('approval_view', '查看审批'),
            ('approval_approve', '审批操作'),
        ]

    def __str__(self):
        return f'[{self.get_approval_type_display()}] {self.title}'


class ApprovalRecord(models.Model):
    """流转记录表 approval_approvalrecord（全程留痕）。"""

    approval = models.ForeignKey(
        Approval, on_delete=models.CASCADE, related_name='records', verbose_name='审批单')
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='操作人')
    action = models.CharField('动作', max_length=20)  # submit / approve / reject
    comment = models.TextField('意见', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '流转记录'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.approval_id} {self.action}'
