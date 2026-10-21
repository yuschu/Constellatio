"""user 插件后台管理。"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, Role, User


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent')
    search_fields = ('name',)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    filter_horizontal = ('permissions',)


@admin.register(User)
class ConstellatioUserAdmin(UserAdmin):
    list_display = ('id', 'username', 'last_name', 'department', 'is_active', 'is_superuser')
    list_filter = ('is_active', 'is_superuser', 'department', 'roles')
    filter_horizontal = ('groups', 'user_permissions', 'roles')
    fieldsets = UserAdmin.fieldsets + (
        ('组织信息', {'fields': ('department', 'roles')}),
    )
