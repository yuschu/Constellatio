from django.apps import AppConfig


class LanguageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.language"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='language',
            version='1.4.0',
            menus=[],
            permissions=[],
            urls='plugins.language.urls',
            signals=[],
            templates=None,
            app=self,
        ))
