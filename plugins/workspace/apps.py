from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkspaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.workspace"

    def ready(self):
        from plugin_host.registry import PluginMeta, register
        register(PluginMeta(
            name='workspace',
            version='1.1.0',
            title=_('插件开关'),
            menus=[
                {'label': _('插件开关'), 'icon': '⚙', 'url': '/plugins/workspace/', 'perm': 'workspace_manage'},
            ],
            permissions=['workspace_manage'],
            urls='plugins.workspace.urls',
            signals=['plugin_toggled'],
            templates='workspace',
            app=self,
        ))
