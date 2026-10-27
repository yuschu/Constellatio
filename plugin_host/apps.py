from django.apps import AppConfig


class PluginHostConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'plugin_host'
    label = 'plugin_host'

    def ready(self):
        # v1.6.1：图表引擎作为 Provider 插件进入注册表（无模型 / 迁移 / URL），
        # 从而复用 workspace 插件开关（DB 运行时启停 + 上链）。
        from django.conf import settings
        from django.utils.translation import gettext_lazy as _

        from .charts import discover_charts
        from .registry import PluginMeta, register

        if discover_charts(settings.BASE_DIR):
            register(PluginMeta(
                name='charts',
                version='1.6.1',
                title=_('图表引擎'),
                menus=[],
                permissions=[],
                urls=None,
                signals=[],
                templates=None,
                app=None,
            ))

        # 注册表完整性校验改为 Django 系统检查（discover.check_registry）：
        # 此处只导入模块完成注册，不直接调用——ready() 时业务插件尚未全部注册。
        from . import discover  # noqa: F401
