"""structure 插件模型：结构应用记录（承载权限码 + 应用留痕）。"""

from django.conf import settings
from django.db import models


class StructureRecord(models.Model):
    """结构模板应用记录表 structure_structurerecord。"""

    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='操作人')
    dept_created = models.PositiveIntegerField('新增部门数', default=0)
    role_created = models.PositiveIntegerField('新增角色数', default=0)
    user_created = models.PositiveIntegerField('新增用户数', default=0)
    grant_manager_perms = models.BooleanField('授权经理管理权限', default=False)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '结构应用记录'
        ordering = ['-applied_at']
        # 插件权限码：迁移自动创建为 Permission
        permissions = [
            ('structure_manage', '结构模板应用'),
            ('structure_view', '查看组织架构'),
        ]

    def __str__(self):
        return f'#{self.pk} +{self.dept_created}部门/+{self.role_created}角色/+{self.user_created}用户'
