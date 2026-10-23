from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LanguageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.language"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='language',
            version='1.5.7',
            title=_('语言'),
            menus=[],
            permissions=[],
            urls='plugins.language.urls',
            signals=[],
            templates=None,
            app=self,
        ))
