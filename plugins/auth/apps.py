from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.auth"
    # label 用 plugin_auth，避免与 django.contrib.auth 的 'auth' 冲突
    label = "plugin_auth"

    def ready(self):
        from plugin_host.registry import PluginMeta, register
        register(PluginMeta(
            name='auth',
            version='0.1.0',
            title=_('认证'),
            # v2.0.9：/ 已由 assistant 的「助手」入口承担；原「工作台」与
            # 「看板」（/dashboard/）指向同一处业务大盘，合并后只保留「看板」。
            menus=[],
            permissions=['auth_login'],
            urls='plugins.auth.urls',
            signals=[],
            templates='auth',
            app=self,
        ))
