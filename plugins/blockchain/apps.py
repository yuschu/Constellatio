from django.apps import AppConfig


class BlockchainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.blockchain"

    def ready(self):
        from plugin_host import signals as bus
        from plugin_host.registry import register, PluginMeta

        # 只订阅信号总线，不反向依赖任何业务插件（跨插件通信只走 signals）
        def _on_approval_finished(sender, **kw):
            BlockchainRecord.append(
                plugin='approval', action='approval_finished',
                payload=f"{kw['approval_id']}:{kw['result']}")

        def _on_notice_published(sender, **kw):
            BlockchainRecord.append(
                plugin='notice', action='notice_published',
                payload=f"announcement:{kw['announcement_id']}")

        def _on_attendance_checked(sender, **kw):
            BlockchainRecord.append(
                plugin='attendance', action='attendance_checked',
                payload=f"{kw['user_id']}:{kw['date']}")

        def _on_user_created(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='user_created',
                payload=f"user:{kw['user_id']}")

        def _on_user_updated(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='user_updated',
                payload=f"user:{kw['user_id']}")

        from .models import BlockchainRecord
        bus.approval_finished.connect(_on_approval_finished, weak=False)
        bus.notice_published.connect(_on_notice_published, weak=False)
        bus.attendance_checked.connect(_on_attendance_checked, weak=False)
        bus.user_created.connect(_on_user_created, weak=False)
        bus.user_updated.connect(_on_user_updated, weak=False)

        register(PluginMeta(
            name='blockchain',
            version='0.6.0',
            menus=[
                {'label': '留痕链', 'icon': '▣', 'url': '/plugins/blockchain/', 'perm': 'blockchain_view'},
            ],
            permissions=['blockchain_view', 'blockchain_verify'],
            urls='plugins.blockchain.urls',
            signals=['approval_finished', 'notice_published',
                     'attendance_checked', 'user_created', 'user_updated'],
            templates='blockchain',
            app=self,
        ))
