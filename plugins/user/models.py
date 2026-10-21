"""user 插件模型：部门 / 角色 / 用户（AUTH_USER_MODEL，RBAC 地基）。"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    """部门表 user_department。"""

    name = models.CharField('部门名称', max_length=100, unique=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='children', verbose_name='上级部门')
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
    """用户表 user_user（AUTH_USER_MODEL）。last_name 存中文姓名。"""

    last_name = models.CharField('姓名', max_length=150, blank=True, default='')
    first_name = models.CharField('备用名', max_length=150, blank=True, default='')
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='members', verbose_name='所属部门')
    roles = models.ManyToManyField(Role, blank=True, related_name='users', verbose_name='角色')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '用户'
        # 插件权限码：迁移时 Django 自动创建为 Permission（codename 即权限码）
        permissions = [
            ('user_manage', '用户与组织管理'),
        ]

    def has_perm(self, perm, obj=None):
        """RBAC 判定链：超管/个人权限放行；否则按角色 → 权限码查询。
        perm 支持 'user_manage' 裸码（插件权限码契约）。"""
        if self.is_superuser:
            return True
        if self.user_permissions.filter(codename=perm).exists():
            return True
        return self.roles.filter(permissions__codename=perm).exists()

    def __str__(self):
        return f'{self.last_name or self.username}'
