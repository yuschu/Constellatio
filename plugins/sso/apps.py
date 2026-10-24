from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SsoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.sso"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='sso',
            version='1.0.0',
            title=_('企业单点登录'),
            menus=[],
            permissions=[],
            urls='plugins.sso.urls',
            signals=['sso_login'],
            templates='sso',
            app=self,
        ))
