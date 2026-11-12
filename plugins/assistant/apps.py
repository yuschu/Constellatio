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
            version='2.0.0',
            title=_('AI 助手'),
            menus=[
                # v2.0.0：对话式首页 + 原看板独立入口。
                # 两条都走 PluginMeta.menus，外壳渲染逻辑不为「看板」单开分支。
                {'label': _('助手'), 'icon': '✦', 'url': '/', 'perm': None},
                {'label': _('看板'), 'icon': '▦', 'url': '/dashboard/', 'perm': None},
            ],
            permissions=[],
            urls='plugins.assistant.urls',
            signals=[],
            templates='assistant',
            app=self,
            home_provider=views.home,
        ))
