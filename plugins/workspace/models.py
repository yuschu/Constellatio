"""workspace 插件模型：插件运行时开关（DB 优先覆盖 settings.OA_PLUGINS）。"""

from django.db import models

from plugin_host.models import AuditModel


class PluginSwitch(AuditModel):
    """插件运行时开关表 workspace_pluginswitch。"""

    app_key = models.CharField('插件标识', max_length=100, unique=True)
    enabled = models.BooleanField('是否启用', default=True)

    class Meta:
        verbose_name = '插件开关'
        # 插件权限码：迁移自动创建为 Permission
        permissions = [('workspace_manage', '插件开关管理')]

    def __str__(self):
        return f'{self.app_key}: {"on" if self.enabled else "off"}'
