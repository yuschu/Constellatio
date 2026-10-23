from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StructureConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.structure"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='structure',
            version='1.5.9',
            title=_('组织架构模板'),
            # v1.5.9：合并「组织架构」与「应用结构」——只保留一个入口，模板详情从页面进入
            menus=[
                {'label': _('组织架构'), 'icon': '◫', 'url': '/plugins/structure/', 'perm': 'structure_view'},
            ],
            permissions=['structure_manage', 'structure_view'],
            urls='plugins.structure.urls',
            signals=['structure_applied'],
            templates='structure',
            app=self,
        ))
