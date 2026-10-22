from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from plugin_host.signals import (
    counter_signature_approved, dept_deleted, user_disabled,
)


class UserConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.user"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='user',
            version='1.2.0',
            title=_('用户与组织'),
            menus=[
                {'label': _('部门'), 'icon': '▣', 'url': '/plugins/user/departments/', 'perm': 'user_manage'},
                {'label': _('用户'), 'icon': '☰', 'url': '/plugins/user/users/', 'perm': 'user_manage'},
                {'label': _('角色'), 'icon': '◆', 'url': '/plugins/user/roles/', 'perm': 'user_manage'},
            ],
            permissions=['user_manage', 'dept_delete_approve', 'user_disable_approve'],
            urls='plugins.user.urls',
            signals=['user_created', 'user_updated', 'user_status_changed', 'user_disabled',
                     'dept_deleted', 'dept_disabled', 'dept_updated', 'password_changed'],
            templates='user',
            app=self,
        ))

        # 跨插件零 import：订阅 approval 会签通过回调，执行物理删除 / 禁用
        def _on_counter_signature_approved(sender, **kw):
            biz_type = kw.get('biz_type')
            biz_id = kw.get('biz_id')
            operator_id = kw.get('operator_id')
            from .models import Department, User
            if biz_type == 'dept_delete':
                dept = Department.objects.filter(pk=biz_id).first()
                if dept:
                    dept_name = dept.name
                    dept.delete()   # 物理删除（会签已全部通过）
                    dept_deleted.send(sender=Department, dept_id=biz_id, dept_name=dept_name,
                                      operator_id=operator_id)
            elif biz_type == 'user_disable':
                target = User.objects.filter(pk=biz_id).first()
                if target:
                    target.permission_frozen = True
                    target.is_active = False
                    target.save(update_fields=['permission_frozen', 'is_active', 'updated_at'])
                    user_disabled.send(sender=User, user_id=biz_id, operator_id=operator_id)

        counter_signature_approved.connect(_on_counter_signature_approved, weak=False)
