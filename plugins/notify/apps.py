"""notify 插件：订阅业务信号写站内信（不反向 import 业务插件）。"""

import logging

from django.apps import AppConfig
from django.apps import apps as dj_apps
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def _model(app_label, model_name):
    try:
        return dj_apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _bulk_create(recipients, *, category, title, body='', link=''):
    """批量写消息；失败不影响业务（插件可停用 / 表未迁移）。"""
    Notification = _model('notify', 'Notification')
    if Notification is None:
        return
    ids = []
    for recipient in recipients:
        if getattr(recipient, 'pk', None):
            ids.append(recipient.pk)
    ids = sorted(set(ids))
    if not ids:
        return
    try:
        Notification.objects.bulk_create([
            Notification(recipient_id=pk, category=category,
                         title=title, body=body, link=link)
            for pk in ids
        ])
    except Exception:      # 通知失败不得影响业务主流程
        logger.exception('站内信写入失败')


class NotifyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.notify"

    def ready(self):
        from plugin_host import signals as bus
        from plugin_host.registry import PluginMeta, register

        def _on_approval_submitted(sender, approval_id, **kw):
            try:
                Approval = _model('approval', 'Approval')
                Signer = _model('approval', 'ApprovalSigner')
                if Approval is None:
                    return
                approval = Approval.objects.filter(pk=approval_id).first()
                if approval is None:
                    return
                recipients = []
                if approval.approver_id:
                    recipients.append(approval.approver)
                if Signer is not None:
                    recipients += [row.signer for row in Signer.objects.filter(
                        approval=approval, signed=False).select_related('signer')]
                recipients += list(approval.cc_users.all())
                recipients = [user for user in recipients
                              if user.pk != approval.applicant_id]
                _bulk_create(
                    recipients,
                    category='approval',
                    title=_('审批待办：%(title)s') % {'title': approval.title},
                    body=_('申请人：%(name)s · 类型：%(type)s') % {
                        'name': approval.applicant.last_name or approval.applicant.username,
                        'type': approval.get_approval_type_display(),
                    },
                    link=f'/plugins/approval/{approval.pk}/',
                )
            except Exception:      # 订阅方失败不得影响业务主流程
                logger.exception('站内信写入失败：审批待办')

        def _on_approval_finished(sender, approval_id, result, **kw):
            try:
                Approval = _model('approval', 'Approval')
                if Approval is None:
                    return
                approval = Approval.objects.filter(pk=approval_id).first()
                if approval is None or approval.applicant_id is None:
                    return
                label = _('已通过') if result == 'approved' else _('已驳回')
                _bulk_create(
                    [approval.applicant],
                    category='approval',
                    title=_('审批结果：%(title)s（%(result)s）') % {
                        'title': approval.title, 'result': label},
                    body=_('类型：%(type)s') % {
                        'type': approval.get_approval_type_display()},
                    link=f'/plugins/approval/{approval.pk}/',
                )
            except Exception:      # 订阅方失败不得影响业务主流程
                logger.exception('站内信写入失败：审批结果')

        def _on_notice_published(sender, announcement_id, **kw):
            try:
                Announcement = _model('notice', 'Announcement')
                User = _model('user', 'User')
                if Announcement is None or User is None:
                    return
                announcement = Announcement.objects.filter(pk=announcement_id).first()
                if announcement is None:
                    return
                recipients = list(User.objects.filter(is_active=True).exclude(
                    pk=announcement.publisher_id))
                _bulk_create(
                    recipients,
                    category='notice',
                    title=_('公告：%(title)s') % {'title': announcement.title},
                    body=_('发布人：%(name)s') % {
                        'name': announcement.publisher.last_name
                        or announcement.publisher.username},
                    link=f'/plugins/notice/?notice={announcement.pk}',
                )
            except Exception:      # 订阅方失败不得影响业务主流程
                logger.exception('站内信写入失败：公告发布')

        bus.approval_submitted.connect(_on_approval_submitted, weak=False)
        bus.approval_finished.connect(_on_approval_finished, weak=False)
        bus.notice_published.connect(_on_notice_published, weak=False)

        register(PluginMeta(
            name='notify',
            version='1.0.0',
            title=_('消息提醒'),
            menus=[{
                'label': _('消息中心'), 'icon': '✉',
                'url': '/plugins/notify/', 'perm': 'notify_view',
            }],
            permissions=['notify_view'],
            urls='plugins.notify.urls',
            signals=['approval_submitted', 'approval_finished', 'notice_published'],
            templates='notify',
            app=self,
        ))
