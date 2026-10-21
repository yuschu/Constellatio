from django.apps import AppConfig


class PluginHostConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'plugin_host'
    label = 'plugin_host'

    def ready(self):
        # Django 会先加载各插件 AppConfig 并执行其 ready()（注册 meta），
        # 此处做注册表完整性校验。
        from .discover import check_registry
        check_registry()
