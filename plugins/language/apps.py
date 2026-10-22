from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LanguageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.language"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='language',
            version='1.4.0',
            title=_('中英文切换'),
            menus=[],
            permissions=[],
            urls='plugins.language.urls',
            signals=[],
            templates=None,
            app=self,
        ))
