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
                # v2.3.0：回到业务页「功能」侧栏，排第一格（order=2；考勤与看板
                # 由首页顶部入口承载，不再占业务侧栏）。名称仍是「插件」，
                # 页面本体按 DSH 插件清单重做。
                {'label': _('插件'), 'icon': 'plugin', 'url': '/plugins/workspace/',
                 'perm': 'workspace_manage', 'order': 2},
            ],
            permissions=['workspace_manage'],
            urls='plugins.workspace.urls',
            signals=['plugin_toggled'],
            templates='workspace',
            app=self,
            builtin=True,   # v2.2.0：插件页自身不进自己的清单
        ))
