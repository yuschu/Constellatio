"""user 插件模型：部门 / 角色 / 用户（AUTH_USER_MODEL，RBAC 地基）。"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from .perms import BASELINE_PERMS, bare_codename


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

    @property
    def level(self):
        """角色等级（v1.5.4）：权限中的最高等级，空权限按 L3。"""
        from .perms import role_level
        return role_level(self)

    @property
    def level_label(self):
        from .perms import LEVEL_LABELS
        return LEVEL_LABELS[self.level]


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
        """RBAC 判定链（v1.5.4）：
        冻结短路 → 超管/未激活 → 全员基线 → 个人权限 → 角色权限码。
        perm 支持 'user_manage' 裸码与 'app.codename' 两种写法。"""
        if self.permission_frozen:
            return False
        if self.is_superuser:
            return True
        if not self.is_active:
            return False
        codename = bare_codename(perm)
        if codename in BASELINE_PERMS:
            return True
        if self.user_permissions.filter(codename=codename).exists():
            return True
        return self.roles.filter(permissions__codename=codename).exists()

    @property
    def level(self):
        """用户等级（v1.5.4）：超管 L0 / 自身权限最高等级。"""
        from .perms import user_level
        return user_level(self)

    @property
    def level_label(self):
        from .perms import LEVEL_LABELS
        return LEVEL_LABELS[self.level]

    def __str__(self):
        return f'{self.last_name or self.username}'
