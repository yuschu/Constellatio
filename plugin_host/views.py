"""容器视图：工作台首页（v1.5.5 待办优先 + 管理员 / 员工视图分流）。"""

from django.apps import apps as dj_apps
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _

from .registry import PLUGIN_REGISTRY, get_enabled_plugins

# 流程快捷发起：审批类型 → (代码, 图标)
APPROVAL_SHORTCUTS = [
    ('leave', _('请假'), '✈'),
    ('expense', _('报销'), '▤'),
    ('seal', _('用章'), '◉'),
    ('outing', _('外出'), '↗'),
    ('overtime', _('加班'), '◷'),
    ('comp', _('调休'), '↺'),
]


def _model(app_label, model_name):
    """动态取插件模型；插件停用 / 未迁移时降级为 None。"""
    try:
        return dj_apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _pending_approvals(user):
    Approval = _model('approval', 'Approval')
    if Approval is None:
        return 0
    return Approval.objects.filter(status='pending').filter(
        Q(approver=user) | Q(signers__signer=user, signers__signed=False)
    ).distinct().count()


def _attendance_today(user):
    """今日考勤待处理：未签到 / 未签退 / 已完成。"""
    Attendance = _model('attendance', 'Attendance')
    if Attendance is None:
        return None
    record = Attendance.objects.filter(
        user=user, date=timezone.localdate()).first()
    if record is None or not record.check_in:
        return {'state': 'todo', 'label': _t('今日未签到'), 'record': record}
    if not record.check_out:
        return {'state': 'todo', 'label': _t('今日未签退'), 'record': record}
    return {'state': 'done', 'label': _t('今日考勤已完成'), 'record': record}


def _recent_notices(limit=3):
    Announcement = _model('notice', 'Announcement')
    if Announcement is None:
        return []
    return list(Announcement.objects.order_by('-is_top', '-created_at')[:limit])


@login_required
def index(request):
    user = request.user
    can_approval = user.has_perm('approval_view')
    can_report = user.has_perm('attendance_report_view')
    can_plugin_ops = user.is_superuser or user.has_perm('workspace_manage')

    shortcuts = [
        {'type': key, 'label': label, 'icon': icon,
         'url': f'/plugins/approval/new/?type={key}'}
        for key, label, icon in APPROVAL_SHORTCUTS
    ] if can_approval else []
    shortcuts.append({
        'type': 'attendance_records' if can_report else 'attendance',
        'label': _t('签到详情') if can_report else _t('我的考勤'),
        'icon': '☷',
        'url': '/plugins/attendance/records/' if can_report else '/plugins/attendance/',
    })

    enabled = get_enabled_plugins()
    return render(request, 'home.html', {
        'pending_approvals': _pending_approvals(user),
        'attendance_today': _attendance_today(user),
        'notices': _recent_notices(),
        'shortcuts': shortcuts,
        'can_approval': can_approval,
        'can_plugin_ops': can_plugin_ops,
        'enabled_plugins': [(key, meta.title) for key, meta in enabled],
        'plugin_total': len(PLUGIN_REGISTRY),
        'enabled_count': len(enabled),
        'is_admin_view': can_plugin_ops,
    })
