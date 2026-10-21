from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.user"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='user',
            version='0.2.0',
            menus=[
                {'label': '部门', 'icon': '▣', 'url': '/plugins/user/departments/', 'perm': 'user_manage'},
                {'label': '用户', 'icon': '☰', 'url': '/plugins/user/users/', 'perm': 'user_manage'},
                {'label': '角色', 'icon': '◆', 'url': '/plugins/user/roles/', 'perm': 'user_manage'},
            ],
            permissions=['user_manage'],
            urls='plugins.user.urls',
            signals=['user_created', 'user_updated'],
            templates='user',
            app=self,
        ))
