from django.apps import AppConfig


class ApprovalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.approval"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='approval',
            version='0.3.0',
            menus=[
                {'label': '审批中心', 'icon': '▣', 'url': '/plugins/approval/', 'perm': 'approval_view'},
                {'label': '待我审批', 'icon': '☐', 'url': '/plugins/approval/pending/', 'perm': 'approval_view'},
            ],
            permissions=['approval_view', 'approval_approve'],
            urls='plugins.approval.urls',
            signals=['approval_finished'],
            templates='approval',
            app=self,
        ))
