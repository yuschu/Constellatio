from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NoticeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.notice"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='notice',
            version='0.4.0',
            title=_('公告通知'),
            menus=[
                # 公告对所有登录用户可见；发布仍由 notice_manage 控制
                {'label': _('公告中心'), 'icon': '▣', 'url': '/plugins/notice/'},
            ],
            permissions=['notice_view', 'notice_manage'],
            urls='plugins.notice.urls',
            signals=['notice_published'],
            templates='notice',
            app=self,
        ))
