from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkspaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.workspace"

    def ready(self):
        from plugin_host.registry import PluginMeta, register
        register(PluginMeta(
            name='workspace',
            version='1.2.0',
            title=_('插件'),
            menus=[
                # v2.0.6：侧栏钉在「助手」之后、「看板」之前（order=2），
                # 名称从「插件开关」收敛为「插件」，页面本体按 DSH 插件清单重做。
                {'label': _('插件'), 'icon': '⧉', 'url': '/plugins/workspace/',
                 'perm': 'workspace_manage', 'order': 2},
            ],
            permissions=['workspace_manage'],
            urls='plugins.workspace.urls',
            signals=['plugin_toggled'],
            templates='workspace',
            app=self,
        ))
