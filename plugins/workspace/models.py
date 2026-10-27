"""workspace 插件模型：插件运行时开关（DB 优先覆盖 settings.OA_PLUGINS）。"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


def _invalidate_switch_cache():
    """局部 import 防止 plugin_host/workspace 循环依赖。"""
    from plugin_host.registry import invalidate_plugin_switch_cache
    invalidate_plugin_switch_cache()


class PluginSwitch(models.Model):
    """插件运行时开关表 workspace_pluginswitch。"""

    app_key = models.CharField('插件标识', max_length=100, unique=True)
    enabled = models.BooleanField('是否启用', default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='最后操作人')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '插件开关'
        # 插件权限码：迁移自动创建为 Permission
        permissions = [('workspace_manage', '插件开关管理')]

    def __str__(self):
        return f'{self.app_key}: {"on" if self.enabled else "off"}'

    def save(self, *args, **kwargs):
        """保存即失效进程内开关缓存（直接 ORM 造数据也立即生效）。"""
        super().save(*args, **kwargs)
        _invalidate_switch_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        _invalidate_switch_cache()
        return result


@receiver(post_delete, sender=PluginSwitch,
          dispatch_uid='workspace.plugin_switch.invalidate_cache')
def _on_switch_deleted(sender, **kwargs):
    """QuerySet.delete() 不调用模型 delete()，用 post_delete 兜底失效。

    save() 走模型覆写即可；本信号只兜批量删除，不作为唯一失效手段。
    """
    _invalidate_switch_cache()
