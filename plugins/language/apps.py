from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LanguageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.language"

    def ready(self):
        from plugin_host.registry import PluginMeta, register
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
            builtin=True,   # v2.2.0：语言随系统内置（设置里的「语言」行），插件页不外显
        ))
