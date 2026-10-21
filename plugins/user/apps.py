from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.user"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='user',
            version='0.2.0',
            menus=[],  # v0.2 提供部门/用户/角色菜单
            permissions=['user_manage'],
            urls='plugins.user.urls',
            signals=[],
            templates='user',
            app=self,
        ))
