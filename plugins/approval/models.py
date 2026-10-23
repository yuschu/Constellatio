"""approval 插件模型：审批单 + 流转记录（状态机 draft→pending→approved/rejected）。"""

from django.conf import settings
from django.db import models


class Approval(models.Model):
    """审批单表 approval_approval。"""

    class Type(models.TextChoices):
        LEAVE = 'leave', '请假'
        EXPENSE = 'expense', '报销'
        SEAL = 'seal', '用章'
        OUTING = 'outing', '外出'
        OVERTIME = 'overtime', '加班'
        COMP = 'comp', '调休'
        DEPT_DELETE = 'dept_delete', '部门删除（会签）'
        USER_DISABLE = 'user_disable', '用户禁用（会签）'

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING = 'pending', '待审批'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已驳回'

    approval_type = models.CharField('审批类型', max_length=20, choices=Type.choices)
    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容', blank=True)
    amount = models.DecimalField('金额', max_digits=12, decimal_places=2, null=True, blank=True)
    biz_id = models.PositiveIntegerField('业务对象ID', null=True, blank=True)  # 会签单：部门ID/用户ID
    # v1.5.5：动态表单数据（请假/报销/用章/外出/加班/调休）
    form_data = models.JSONField('表单数据', default=dict, blank=True)
    # v1.5.14：用章申请附件（单个文件，下载走权限视图）
    attachment = models.FileField(
        '用章附件', upload_to='approval_attachments/%Y/%m/', null=True, blank=True)
    department_id = models.PositiveIntegerField('部门ID', null=True, blank=True)
    department_name = models.CharField('部门名称', max_length=100, blank=True, default='')
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='approvals', verbose_name='申请人')
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='approval_tasks', verbose_name='审批人',
        null=True, blank=True)
    # v1.5.5：抄送人（审批人上级、结果抄送）
    cc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='cc_approvals',
        verbose_name='抄送人')
    status = models.CharField(
        '状态', max_length=20, choices=Status.choices, default=Status.DRAFT)
    # v1.5.16：申请人在「我发起的」里隐藏已驳回申请（仅隐藏，不删除留痕）
    applicant_hidden = models.BooleanField('申请人已隐藏', default=False)
    # v1.5.17：重新申请后指向替换该驳回单的新单
    replaced_by = models.OneToOneField(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='replaces_rejected', verbose_name='替换为')
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

    def is_counter_signature(self):
        """是否会签单（部门删除 / 用户禁用）。"""
        return self.approval_type in (self.Type.DEPT_DELETE, self.Type.USER_DISABLE)

    def __str__(self):
        return f'[{self.get_approval_type_display()}] {self.title}'


class ApprovalSigner(models.Model):
    """会签人表 approval_approvalsigner（会签单：全部 signer 通过才通过）。"""

    approval = models.ForeignKey(
        Approval, on_delete=models.CASCADE, related_name='signers', verbose_name='审批单')
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='会签人')
    signed = models.BooleanField('已签', default=False)
    signed_at = models.DateTimeField('签批时间', null=True, blank=True)
    comment = models.TextField('意见', blank=True)

    class Meta:
        verbose_name = '会签人'
        unique_together = ('approval', 'signer')

    def __str__(self):
        return f'{self.approval_id} {self.signer_id} {"✓" if self.signed else "—"}'


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
