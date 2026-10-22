from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.auth"
    # label 用 plugin_auth，避免与 django.contrib.auth 的 'auth' 冲突
    label = "plugin_auth"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='auth',
            version='0.1.0',
            title=_('认证'),
            menus=[{'label': _('工作台'), 'icon': '⌂', 'url': '/'}],
            permissions=['auth_login'],
            urls='plugins.auth.urls',
            signals=[],
            templates='auth',
            app=self,
        ))
