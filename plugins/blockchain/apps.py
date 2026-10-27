import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class BlockchainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.blockchain"

    def ready(self):
        from plugin_host import signals as bus
        from plugin_host.registry import PluginMeta, register

        # 只订阅信号总线，不反向依赖任何业务插件（跨插件通信只走 signals）。
        # v1.7.x：每个 handler 内部兜底异常，留痕写入失败不得炸上游业务（审批/打卡）。
        def _safe(label, handler):
            """包一层：handler 抛异常时记日志并吞掉，信号发送方不受影响。"""
            def wrapper(sender, **kw):
                try:
                    return handler(sender, **kw)
                except Exception:      # 订阅方失败不得影响业务主流程
                    logger.exception('留痕写入失败：%s', label)
            return wrapper

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

        def _on_structure_applied(sender, **kw):
            BlockchainRecord.append(
                plugin='structure', action='structure_applied',
                payload=f"+{kw['dept_created']}dept/+{kw['role_created']}role/+{kw['user_created']}user",
                operator_id=kw.get('applied_by_id'))

        from .models import BlockchainRecord
        bus.approval_finished.connect(
            _safe('approval_finished', _on_approval_finished), weak=False)
        bus.notice_published.connect(
            _safe('notice_published', _on_notice_published), weak=False)
        bus.attendance_checked.connect(
            _safe('attendance_checked', _on_attendance_checked), weak=False)
        bus.user_created.connect(
            _safe('user_created', _on_user_created), weak=False)
        bus.user_updated.connect(
            _safe('user_updated', _on_user_updated), weak=False)
        bus.plugin_toggled.connect(
            _safe('plugin_toggled', _on_plugin_toggled), weak=False)
        bus.dept_deleted.connect(
            _safe('dept_deleted', _on_dept_deleted), weak=False)
        bus.dept_disabled.connect(
            _safe('dept_disabled', _on_dept_disabled), weak=False)
        bus.dept_updated.connect(
            _safe('dept_updated', _on_dept_updated), weak=False)
        bus.user_status_changed.connect(
            _safe('user_status_changed', _on_user_status_changed), weak=False)
        bus.user_disabled.connect(
            _safe('user_disabled', _on_user_disabled), weak=False)
        bus.password_changed.connect(
            _safe('password_changed', _on_password_changed), weak=False)
        bus.structure_applied.connect(
            _safe('structure_applied', _on_structure_applied), weak=False)

        register(PluginMeta(
            name='blockchain',
            version='1.3.0',
            title=_('操作留痕链'),
            menus=[
                {'label': _('留痕链'), 'icon': '▣', 'url': '/plugins/blockchain/', 'perm': 'blockchain_view'},
            ],
            permissions=['blockchain_view', 'blockchain_verify'],
            urls='plugins.blockchain.urls',
            signals=['approval_finished', 'notice_published', 'attendance_checked',
                     'user_created', 'user_updated', 'plugin_toggled',
                     'dept_deleted', 'dept_disabled', 'dept_updated',
                     'user_status_changed', 'user_disabled', 'password_changed',
                     'structure_applied'],
            templates='blockchain',
            app=self,
        ))
