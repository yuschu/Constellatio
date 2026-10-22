from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StructureConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.structure"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='structure',
            version='1.3.0',
            menus=[
                {'label': _('组织架构'), 'icon': '◫', 'url': '/plugins/structure/', 'perm': 'structure_view'},
                {'label': _('应用结构'), 'icon': '⤓', 'url': '/plugins/structure/apply/', 'perm': 'structure_manage'},
            ],
            permissions=['structure_manage', 'structure_view'],
            urls='plugins.structure.urls',
            signals=['structure_applied'],
            templates='structure',
            app=self,
        ))
