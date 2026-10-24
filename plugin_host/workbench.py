"""工作台数据聚合（v1.6.2）：时间范围 / 角色 → 指标 + 图表 payload。

跨插件数据一律走 apps.get_model（不 import 业务插件），插件停用 / 未迁移时降级。
图表只产出 ChartRenderer 契约的 payload；模板在图表停用时用数字 / 表格降级。
"""

from datetime import datetime, time, timedelta

from django.apps import apps as dj_apps
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from django.utils.translation import gettext as _t

from plugin_host.charts import chart_switch_enabled
from plugin_host.registry import PLUGIN_REGISTRY

RANGE_KEYS = ('today', 'week', 'month')
DEFAULT_RANGE = 'month'
TODO_ALERT_THRESHOLD = 3
FLOW_TYPES = ('leave', 'expense', 'seal', 'outing', 'overtime')
FLOW_LABELS = {
    'leave': '请假',
    'expense': '报销',
    'seal': '用章',
    'outing': '外出',
    'overtime': '加班',
}
RANGE_LABELS = {'today': '今日', 'week': '本周', 'month': '本月'}
WINDOW_LABELS = {'today': '今日 · 24 小时', 'week': '近 7 天', 'month': '近 30 天'}


def _model(app_label, model_name):
    try:
        return dj_apps.get_model(app_label, model_name)
    except LookupError:
        return None


def parse_range(raw):
    return raw if raw in RANGE_KEYS else DEFAULT_RANGE


def _window(range_key, now):
    """(起始 aware datetime, 起始 date, 天数)。"""
    today = now.date()
    if range_key == 'today':
        start_date, days = today, 1
    elif range_key == 'week':
        start_date, days = today - timedelta(days=6), 7
    else:
        start_date, days = today - timedelta(days=29), 30
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    return start, start_date, days


def _bucket_axis(range_key, now):
    """返回 (mode, keys, labels)：mode=hour（今日）/ date（周、月）。"""
    if range_key == 'today':
        return 'hour', list(range(24)), [f'{hour:02d}:00' for hour in range(24)]
    days = 7 if range_key == 'week' else 30
    start = now.date() - timedelta(days=days - 1)
    keys = [start + timedelta(days=offset) for offset in range(days)]
    return 'date', keys, [day.strftime('%m-%d') for day in keys]


def _bucket_value(bucket, mode):
    if mode == 'hour':
        return timezone.localtime(bucket).hour
    return bucket


def _approval_counts(base, mode):
    trunc = TruncHour if mode == 'hour' else TruncDate
    counts = {}
    rows = (base.annotate(bucket=trunc('created_at'))
                .values('bucket', 'approval_type')
                .annotate(n=Count('id')))
    for row in rows:
        key = _bucket_value(row['bucket'], mode)
        counts[(key, row['approval_type'])] = row['n']
    return counts


def _flow_counts(base):
    counts = {key: 0 for key in FLOW_TYPES}
    for row in base.values('approval_type').annotate(n=Count('id')):
        if row['approval_type'] in counts:
            counts[row['approval_type']] = row['n']
    return counts


def _plugin_label(key):
    from plugin_host.registry import PLUGIN_REGISTRY
    meta = PLUGIN_REGISTRY.get(key)
    return str(meta.title) if meta else key


def _payload(chart, **kwargs):
    return chart.payload(**kwargs) if chart is not None else None


def build_dashboard(*, user, is_admin, enabled_names, range_key, chart,
                    pending_approvals, attendance_today):
    """组装看板上下文（cards / trend / pie / dept / range_links）。"""
    now = timezone.localtime()
    start, start_date, _days = _window(range_key, now)
    mode, bucket_keys, bucket_labels = _bucket_axis(range_key, now)
    range_label = _t(RANGE_LABELS[range_key])
    window_label = _t(WINDOW_LABELS[range_key])

    cards = {}
    trend = None
    pie = None
    dept = None

    Approval = _model('approval', 'Approval')
    Attendance = _model('attendance', 'Attendance')
    if Approval is not None and 'approval' in enabled_names:
        base = Approval.objects.filter(created_at__range=(start, now))
        scope = base if is_admin else base.filter(applicant=user)

        # 待我审批：当前待办（实时）+ 窗口内完成率
        mine = base.filter(approver=user)
        total = mine.count()
        done = mine.filter(status__in=('approved', 'rejected')).count()
        percent = round(done * 100 / total) if total else 0
        cards['approval'] = {
            'pending': pending_approvals,
            'total': total,
            'done': done,
            'percent': percent,
            'alert': pending_approvals >= TODO_ALERT_THRESHOLD,
            'payload': _payload(
                chart, kind='gauge', compact=True,
                series=[{'name': _t('完成率'), 'value': percent}],
                link='/plugins/approval/pending/'),
        }

        # 流程发起：五类单据计数
        flow = _flow_counts(scope)
        flow_total = sum(flow.values())
        cards['flow'] = {
            'total': flow_total,
            'counts': [{'key': key, 'label': _t(FLOW_LABELS[key]), 'count': flow[key]}
                       for key in FLOW_TYPES],
            'payload': _payload(
                chart, kind='cartesian', compact=True,
                categories=[_t(FLOW_LABELS[key]) for key in FLOW_TYPES],
                series=[{'name': _t('单据数'),
                         'data': [flow[key] for key in FLOW_TYPES],
                         'type': 'bar', 'stack': False}],
                link='/plugins/approval/'),
        }

        # 流程趋势大盘：按桶 × 类型
        counts = _approval_counts(scope, mode)
        series = [{
            'key': key,
            'label': _t(FLOW_LABELS[key]),
            'data': [counts.get((bucket, key), 0) for bucket in bucket_keys],
        } for key in FLOW_TYPES]
        trend = {
            'window_label': window_label,
            'categories': bucket_labels,
            'series': series,
            'totals': [{'label': item['label'], 'count': sum(item['data'])}
                       for item in series],
            'payload': _payload(
                chart, kind='cartesian',
                categories=bucket_labels,
                series=[{'name': item['label'], 'data': item['data'], 'type': 'line'}
                        for item in series],
                link='/plugins/approval/'),
        }

    if Attendance is not None and 'attendance' in enabled_names:
        # 考勤概况：个人逐桶打卡记录 + 今日状态
        if mode == 'hour':
            records = Attendance.objects.filter(
                user=user, date=start_date, check_in__isnull=False)
            rows = (records.annotate(bucket=TruncHour('check_in'))
                           .values('bucket').annotate(n=Count('id')))
            counts = {_bucket_value(row['bucket'], mode): row['n'] for row in rows}
            checked_days = 1 if records.exists() else 0
        else:
            records = Attendance.objects.filter(
                user=user, date__range=(start_date, now.date()))
            rows = records.values('date').annotate(n=Count('id'))
            counts = {row['date']: row['n'] for row in rows}
            checked_days = records.values('date').distinct().count()
        cards['attendance'] = {
            'state': (attendance_today or {}).get('state', 'todo'),
            'label': (attendance_today or {}).get('label', _t('今日未签到')),
            'checked_days': checked_days,
            'payload': _payload(
                chart, kind='cartesian', compact=True,
                categories=bucket_labels,
                series=[{'name': _t('打卡'),
                         'data': [counts.get(bucket, 0) for bucket in bucket_keys],
                         'type': 'line'}],
                link='/plugins/attendance/'),
        }

    # 插件运行状态（管理员）
    if is_admin:
        total_plugins = len(PLUGIN_REGISTRY)
        chart_on = chart_switch_enabled()
        enabled_count = len(enabled_names) + (
            1 if 'charts' in PLUGIN_REGISTRY and chart_on else 0)
        percent = round(enabled_count * 100 / total_plugins) if total_plugins else 0
        cards['plugins'] = {
            'enabled': enabled_count,
            'total': total_plugins,
            'percent': percent,
            'alert': enabled_count < total_plugins,
            'payload': _payload(
                chart, kind='gauge', compact=True,
                series=[{'name': _t('启用率'), 'value': percent}],
                link='/plugins/workspace/'),
        }

        # 插件分布饼图：窗口内留痕活跃度
        BlockchainRecord = _model('blockchain', 'BlockchainRecord')
        if BlockchainRecord is not None and 'blockchain' in enabled_names:
            rows = (BlockchainRecord.objects
                    .filter(created_at__range=(start, now))
                    .values('plugin').annotate(n=Count('id')).order_by('-n'))
            pie_rows = [{'key': row['plugin'], 'label': _plugin_label(row['plugin']),
                         'value': row['n']} for row in rows]
            pie = {
                'rows': pie_rows,
                'total': sum(row['value'] for row in pie_rows),
                'payload': _payload(
                    chart, kind='pie',
                    series=[{'name': row['label'], 'value': row['value']}
                            for row in pie_rows],
                    link='/plugins/blockchain/') if pie_rows else None,
            }

        # 组织人员柱状图：部门人数 / 今日签到 / 待审批（按审批人部门）
        Department = _model('user', 'Department')
        if Department is not None and 'user' in enabled_names:
            departments = list(
                Department.objects.filter(is_active=True)
                .annotate(headcount=Count('members', filter=Q(members__is_active=True)))
                .order_by('-headcount', 'name')[:10])
            dept_ids = [item.id for item in departments]
            today_checked = {}
            if Attendance is not None:
                today_checked = {
                    row['user__department_id']: row['n']
                    for row in Attendance.objects.filter(
                        date=now.date(), check_in__isnull=False,
                        user__department_id__in=dept_ids)
                    .values('user__department_id')
                    .annotate(n=Count('user', distinct=True))
                }
            pending_map = {
                row['approver__department_id']: row['n']
                for row in Approval.objects.filter(
                    status='pending', approver__department_id__in=dept_ids)
                .values('approver__department_id').annotate(n=Count('id'))
            }
            rows = [{
                'name': item.name,
                'headcount': item.headcount,
                'checked': today_checked.get(item.id, 0),
                'pending': pending_map.get(item.id, 0),
            } for item in departments]
            dept = {
                'rows': rows,
                'payload': _payload(
                    chart, kind='cartesian',
                    categories=[item.name for item in departments],
                    series=[
                        {'name': _t('部门人数'),
                         'data': [item.headcount for item in departments],
                         'type': 'bar', 'stack': False},
                        {'name': _t('今日签到'),
                         'data': [today_checked.get(item.id, 0) for item in departments],
                         'type': 'bar', 'stack': False},
                        {'name': _t('待审批'),
                         'data': [pending_map.get(item.id, 0) for item in departments],
                         'type': 'bar', 'stack': False},
                    ],
                    link='/plugins/structure/') if departments else None,
            }

    range_links = [{
        'key': key,
        'label': _t(RANGE_LABELS[key]),
        'url': f'/?range={key}',
        'active': key == range_key,
    } for key in RANGE_KEYS]

    return {
        'range_key': range_key,
        'range_label': range_label,
        'range_links': range_links,
        'cards': cards,
        'trend': trend,
        'pie': pie,
        'dept': dept,
    }
