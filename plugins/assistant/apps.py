from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AssistantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'plugins.assistant'
    verbose_name = _('AI 助手')

    def ready(self):
        from plugin_host.registry import PluginMeta, register

        from . import views

        register(PluginMeta(
            name='assistant',
            version='2.3.0',
            title=_('AI 助手'),
            # v2.2.1：菜单清空——看板入口已挪到容器的 builtin core。
            # 停用助手插件只该关掉「新会话」与对话输入，不能再连带摘掉看板入口。
            menus=[],
            permissions=[],
            urls='plugins.assistant.urls',
            signals=[],
            templates='assistant',
            app=self,
            home_provider=views.home,
        ))
