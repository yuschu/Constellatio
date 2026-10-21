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

    def __str__(self):
        return f'{self.last_name or self.username}'
