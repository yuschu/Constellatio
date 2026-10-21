"""user 插件模型：部门 / 角色 / 用户（AUTH_USER_MODEL，RBAC 地基）。"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    """部门表 user_department（支持软删：is_active=False 即停用，硬删走会签审批）。"""

    name = models.CharField('部门名称', max_length=100, unique=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='children', verbose_name='上级部门')
    is_active = models.BooleanField('是否启用', default=True)   # 软删标记
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '部门'

    def __str__(self):
        return self.name


class Role(models.Model):
    """角色表 user_role。"""

    name = models.CharField('角色名', max_length=100, unique=True)
    permissions = models.ManyToManyField('auth.Permission', blank=True, verbose_name='权限')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '角色'

    def __str__(self):
        return self.name


class User(AbstractUser):
    """用户表 user_user（AUTH_USER_MODEL）。last_name 存中文姓名。

    状态机：is_active（可登录）+ permission_frozen（权限冻结，即时短路 has_perm）。
    权限层级：超管 L0 最高，其他任何用户操作目标为超管一律拒绝。
    """

    last_name = models.CharField('姓名', max_length=150, blank=True, default='')
    first_name = models.CharField('备用名', max_length=150, blank=True, default='')
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='members', verbose_name='所属部门')
    roles = models.ManyToManyField(Role, blank=True, related_name='users', verbose_name='角色')
    permission_frozen = models.BooleanField('权限冻结', default=False)   # 冻结权限：登录但无操作权限
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '用户'
        # 插件权限码：迁移时 Django 自动创建为 Permission（codename 即权限码）
        permissions = [
            ('user_manage', '用户与组织管理'),
            ('dept_delete_approve', '部门删除审批'),
            ('user_disable_approve', '用户禁用审批'),
        ]

    def has_perm(self, perm, obj=None):
        """RBAC 判定链：权限冻结即时短路；超管/个人权限放行；否则按角色 → 权限码查询。
        perm 支持 'user_manage' 裸码（插件权限码契约）。"""
        if self.permission_frozen:
            return False
        if self.is_superuser:
            return True
        if self.user_permissions.filter(codename=perm).exists():
            return True
        return self.roles.filter(permissions__codename=perm).exists()

    def __str__(self):
        return f'{self.last_name or self.username}'
