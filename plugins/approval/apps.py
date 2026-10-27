from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ApprovalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.approval"

    def ready(self):
        from plugin_host.registry import PluginMeta, register
        register(PluginMeta(
            name='approval',
            version='1.3.0',
            title=_('审批中心'),
            menus=[
                {'label': _('审批中心'), 'icon': '▣', 'url': '/plugins/approval/', 'perm': 'approval_view'},
                # v1.5.15：待我审批仅管理岗可见（L3 隐藏）
                {'label': _('待我审批'), 'icon': '☐', 'url': '/plugins/approval/pending/', 'perm': 'approval_approve'},
                {'label': _('抄送我的'), 'icon': '✉', 'url': '/plugins/approval/cc/', 'perm': 'approval_approve'},
            ],
            permissions=['approval_view', 'approval_approve'],
            urls='plugins.approval.urls',
            signals=['approval_finished', 'counter_signature_approved'],
            templates='approval',
            app=self,
        ))

        # 跨插件零 import：订阅 user 插件的会签请求信号 → 创建会签审批单
        def _signers_for(perm_codename):
            """具备权限码的管理员集合（含超管；排除已冻结/禁用的用户）。"""
            from django.apps import apps as dj_apps
            User = dj_apps.get_model('user', 'User')
            users = User.objects.filter(is_active=True)
            return [u for u in users if u.has_perm(perm_codename)]

        def _on_dept_delete_requested(sender, **kw):
            from django.apps import apps as dj_apps

            from .models import Approval
            from .services import start_counter_signature
            User = dj_apps.get_model('user', 'User')
            operator = User.objects.filter(pk=kw['operator_id']).first()
            if operator is None:
                return
            approval = Approval.objects.create(
                approval_type=Approval.Type.DEPT_DELETE,
                title=kw.get('title', '部门删除审批'),
                content=kw.get('content', ''),
                applicant=operator,
                approver=operator,
                biz_id=kw['dept_id'])
            try:
                start_counter_signature(
                    approval, _signers_for('dept_delete_approve'), operator, '系统发起：部门删除会签')
            except ValueError:
                approval.status = Approval.Status.REJECTED
                approval.save(update_fields=['status', 'updated_at'])

        def _on_user_disable_requested(sender, **kw):
            from django.apps import apps as dj_apps

            from .models import Approval
            from .services import start_counter_signature
            User = dj_apps.get_model('user', 'User')
            operator = User.objects.filter(pk=kw['operator_id']).first()
            if operator is None:
                return
            approval = Approval.objects.create(
                approval_type=Approval.Type.USER_DISABLE,
                title=kw.get('title', '用户禁用审批'),
                content=kw.get('content', ''),
                applicant=operator,
                approver=operator,
                biz_id=kw['user_id'])
            try:
                start_counter_signature(
                    approval, _signers_for('user_disable_approve'), operator, '系统发起：用户禁用会签')
            except ValueError:
                approval.status = Approval.Status.REJECTED
                approval.save(update_fields=['status', 'updated_at'])

        from plugin_host.signals import dept_delete_requested, user_disable_requested
        dept_delete_requested.connect(_on_dept_delete_requested, weak=False)
        user_disable_requested.connect(_on_user_disable_requested, weak=False)
