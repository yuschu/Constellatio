"""容器视图：工作台首页（v1.5.5 待办优先 + 管理员 / 员工视图分流） + 主题切换（v1.5.8）。"""

from django.apps import apps as dj_apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from .registry import get_enabled_plugins, plugin_counts
from .theming import THEME_COOKIE_NAME, discover_themes

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


def _recent_notifications(user, limit=3):
    """v1.7.0：工作台「我的消息」预览（仅本人）。"""
    Notification = _model('notify', 'Notification')
    if Notification is None:
        return []
    return list(Notification.objects.filter(
        recipient=user).order_by('-created_at')[:limit])


@login_required
def index(request):
    user = request.user
    can_approval = user.has_perm('approval_view')
    can_approve = user.has_perm('approval_approve')   # v1.5.15：L3 不显示「待我审批」
    can_report = user.has_perm('attendance_report_view')
    can_plugin_ops = user.is_superuser or user.has_perm('workspace_manage')

    # v1.5.7：入口随插件启停收敛——停用的插件不再出现在工作台卡片 / 快捷入口
    enabled = get_enabled_plugins()
    enabled_names = {key for key, _ in enabled}

    shortcuts = [
        {'type': key, 'label': label, 'icon': icon,
         'url': f'/plugins/approval/new/?type={key}'}
        for key, label, icon in APPROVAL_SHORTCUTS
    ] if can_approval and 'approval' in enabled_names else []
    if 'attendance' in enabled_names:
        shortcuts.append({
            'type': 'attendance_records' if can_report else 'attendance',
            'label': _t('签到详情') if can_report else _t('我的考勤'),
            'icon': '☷',
            'url': '/plugins/attendance/records/' if can_report else '/plugins/attendance/',
        })

    pending = (_pending_approvals(user)
               if 'approval' in enabled_names and can_approve else 0)
    attendance_today = _attendance_today(user) if 'attendance' in enabled_names else None

    # v1.6.2：工作台图表大盘——范围筛选 + 角色分流（管理员 / 员工）
    from .charts import get_active_chart
    from .workbench import build_dashboard, parse_range

    dashboard = build_dashboard(
        user=user,
        is_admin=can_plugin_ops,
        enabled_names=enabled_names,
        range_key=parse_range(request.GET.get('range')),
        chart=get_active_chart(),
        pending_approvals=pending,
        attendance_today=attendance_today,
    )
    plugin_enabled_count, plugin_total = plugin_counts()

    return render(request, 'home.html', {
        'pending_approvals': pending,
        'attendance_today': attendance_today,
        'notices': _recent_notices() if 'notice' in enabled_names else [],
        'messages_preview': (_recent_notifications(user)
                             if 'notify' in enabled_names else []),
        'shortcuts': shortcuts,
        'can_approval': can_approval,
        'can_approve': can_approve,
        'can_plugin_ops': can_plugin_ops,
        'enabled_plugins': [(key, meta.title) for key, meta in enabled],
        'plugin_total': plugin_total,
        'enabled_count': plugin_enabled_count,
        'is_admin_view': can_plugin_ops,
        **dashboard,
    })


@require_POST
def theme_switch(request):
    """v1.5.8：切换主题（POST theme=<key>），写 Cookie 后回到 next / Referer / 工作台。"""
    key = request.POST.get('theme')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        next_url = '/'

    response = redirect(next_url)
    if key in discover_themes(settings.BASE_DIR):
        response.set_cookie(
            THEME_COOKIE_NAME, key,
            max_age=settings.THEME_COOKIE_AGE, samesite='Lax')
    return response
