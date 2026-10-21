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

        def _on_plugin_toggled(sender, **kw):
            BlockchainRecord.append(
                plugin='workspace', action='plugin_toggled',
                payload=f"{kw['app_key']}:{kw['enabled']}",
                operator_id=kw.get('operator_id'))

        # ---- v1.2：部门软/硬删/修改、用户状态/禁用、密码变更 全部留痕 ----
        def _on_dept_deleted(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='dept_deleted',
                payload=f"{kw['dept_id']}:{kw.get('dept_name', '')}",
                operator_id=kw.get('operator_id'))

        def _on_dept_disabled(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='dept_disabled',
                payload=f"dept:{kw['dept_id']}", operator_id=kw.get('operator_id'))

        def _on_dept_updated(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='dept_updated',
                payload=f"dept:{kw['dept_id']}", operator_id=kw.get('operator_id'))

        def _on_user_status_changed(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='user_status_changed',
                payload=f"user:{kw['user_id']}:{kw['status']}",
                operator_id=kw.get('operator_id'))

        def _on_user_disabled(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='user_disabled',
                payload=f"user:{kw['user_id']}", operator_id=kw.get('operator_id'))

        def _on_password_changed(sender, **kw):
            BlockchainRecord.append(
                plugin='user', action='password_changed',
                payload=f"user:{kw['user_id']}", operator_id=kw.get('operator_id'))

        from .models import BlockchainRecord
        bus.approval_finished.connect(_on_approval_finished, weak=False)
        bus.notice_published.connect(_on_notice_published, weak=False)
        bus.attendance_checked.connect(_on_attendance_checked, weak=False)
        bus.user_created.connect(_on_user_created, weak=False)
        bus.user_updated.connect(_on_user_updated, weak=False)
        bus.plugin_toggled.connect(_on_plugin_toggled, weak=False)
        bus.dept_deleted.connect(_on_dept_deleted, weak=False)
        bus.dept_disabled.connect(_on_dept_disabled, weak=False)
        bus.dept_updated.connect(_on_dept_updated, weak=False)
        bus.user_status_changed.connect(_on_user_status_changed, weak=False)
        bus.user_disabled.connect(_on_user_disabled, weak=False)
        bus.password_changed.connect(_on_password_changed, weak=False)

        register(PluginMeta(
            name='blockchain',
            version='1.2.0',
            menus=[
                {'label': '留痕链', 'icon': '▣', 'url': '/plugins/blockchain/', 'perm': 'blockchain_view'},
            ],
            permissions=['blockchain_view', 'blockchain_verify'],
            urls='plugins.blockchain.urls',
            signals=['approval_finished', 'notice_published', 'attendance_checked',
                     'user_created', 'user_updated', 'plugin_toggled',
                     'dept_deleted', 'dept_disabled', 'dept_updated',
                     'user_status_changed', 'user_disabled', 'password_changed'],
            templates='blockchain',
            app=self,
        ))
