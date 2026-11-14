"""工作台数据聚合（v1.6.2）：时间范围 / 角色 → 指标 + 图表 payload。

跨插件数据一律走 apps.get_model（不 import 业务插件），插件停用 / 未迁移时降级。
图表只产出 ChartRenderer 契约的 payload；模板在图表停用时用数字 / 表格降级。
"""

import logging
from datetime import datetime, time, timedelta

from django.apps import apps as dj_apps
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.translation import gettext as _t

from plugin_host.registry import PLUGIN_REGISTRY, plugin_counts

logger = logging.getLogger(__name__)

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


def _degraded(block):
    """跨插件区块数据不可用：记 warning 并保留降级结构（不 500）。"""
    logger.warning('工作台区块 %s 不可用，已降级', block, exc_info=True)


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
    meta = PLUGIN_REGISTRY.get(key)
    return str(meta.title) if meta else key


def _composition_of(flow_card):
    """把「流程发起」的五类计数折成环形图段（dsh-context donut.tsx 的弧长算法）。

    viewBox 0 0 42 42、r=15.9155 的整圆周长正好 100，所以百分比可以直接当
    strokeDasharray 用；多段时每段两端各切 SEG_GAP/2（最多切到段长的 1/4）。
    """
    if not flow_card:
        return {'segments': [], 'total': 0}
    counts = flow_card.get('counts') or []
    total = sum(item['count'] for item in counts)
    segments = []
    acc = 0.0
    for index, item in enumerate(counts):
        if total <= 0 or item['count'] <= 0:
            continue
        share = item['count'] * 100 / total
        segments.append({
            'key': item['key'],
            'label': item['label'],
            'count': item['count'],
            'share': round(share, 1),
            'length': round(share, 2),
            'offset': round(100 - acc + 25, 2),
            'tone': index + 1,
        })
        acc += share
    if len(segments) > 1:
        for seg in segments:
            cut = min(0.25, seg['length'] / 4)
            seg['length'] = round(seg['length'] - cut * 2, 2)
            seg['offset'] = round(seg['offset'] - cut, 2)
    for seg in segments:
        seg['rest'] = round(100 - seg['length'], 2)
    return {'segments': segments, 'total': total}


def _payload(chart, **kwargs):
    return chart.payload(**kwargs) if chart is not None else None


HEAT_WEEKS = 8          # dsh-context 活跃度卡默认 8 周
USAGE_DAYS = 7          # 近 7 天用量卡固定 7 列
HEAT_LEVELS = (0.25, 0.5, 0.75)   # 热力分档阈值（dsh-context heatmap.tsx 的 levelOf）


def _build_insight(*, user, is_admin, enabled_names, now):
    """dsh-context「上下文洞察」版式需要的两段时间序列。

    - usage7：近 7 天「提交 / 已办结」双柱。DSH 的用量图按「会话自身各请求的时间」
      汇总，这里同口径按单据创建日归属，已办结也按创建日归到同一天。
    - heat：近 8 周每日签到活跃度。管理员按「当天签到人数去重」，员工只看本人记录，
      单位因此统一成「人天」，对应 DSH 热力图的 sessions 指标。

    降级约定与 build_dashboard 一致：插件停用 / 表未迁移时返回空序列，不抛异常。
    """
    today = now.date()
    span_start = today - timedelta(days=HEAT_WEEKS * 7 - 1)
    usage_days = [today - timedelta(days=offset)
                  for offset in range(USAGE_DAYS - 1, -1, -1)]

    Approval = _model('approval', 'Approval')
    Attendance = _model('attendance', 'Attendance')

    submitted = {}
    finished = {}
    if Approval is not None and 'approval' in enabled_names:
        try:
            base = Approval.objects.filter(created_at__date__gte=usage_days[0])
            if not is_admin:
                base = base.filter(applicant=user)
            for row in (base.annotate(day=TruncDate('created_at'))
                            .values('day').annotate(n=Count('id'))):
                submitted[row['day']] = row['n']
            for row in (base.filter(status__in=('approved', 'rejected'))
                            .annotate(day=TruncDate('created_at'))
                            .values('day').annotate(n=Count('id'))):
                finished[row['day']] = row['n']
        except (OperationalError, ProgrammingError):
            _degraded('insight.approval')

    heat_counts = {}
    if Attendance is not None and 'attendance' in enabled_names:
        try:
            rows = Attendance.objects.filter(
                date__range=(span_start, today), check_in__isnull=False)
            if is_admin:
                for row in (rows.values('date')
                                .annotate(n=Count('user', distinct=True))):
                    heat_counts[row['date']] = row['n']
            else:
                for row in rows.filter(user=user).values('date'):
                    heat_counts[row['date']] = 1
        except (OperationalError, ProgrammingError):
            _degraded('insight.attendance')

    max_submitted = max([submitted.get(day, 0) for day in usage_days] + [0])
    max_finished = max([finished.get(day, 0) for day in usage_days] + [0])

    def _height(value, peak):
        if peak <= 0 or value <= 0:
            return 0
        return max(4, round(value * 100 / peak))

    usage7 = [{
        'key': day.isoformat(),
        'label': day.strftime('%m-%d'),
        'submitted': submitted.get(day, 0),
        'finished': finished.get(day, 0),
        'submitted_height': _height(submitted.get(day, 0), max_submitted),
        'finished_height': _height(finished.get(day, 0), max_finished),
    } for day in usage_days]
    usage7_ticks = [{
        'percent': percent,
        'top': 100 - percent,
        'submitted_label': round(max_submitted * percent / 100),
        'finished_label': round(max_finished * percent / 100),
    } for percent in (0, 25, 50, 75, 100)]

    # 热力网格：列 = 周（周日起），行 = 星期 0..6，最后一列是本周
    last_sunday = today - timedelta(days=today.isoweekday() % 7)
    first_sunday = last_sunday - timedelta(days=7 * (HEAT_WEEKS - 1))
    span_days = [span_start + timedelta(days=offset)
                 for offset in range((today - span_start).days + 1)]
    peak = max([heat_counts.get(day, 0) for day in span_days] + [0])
    heat_cols = []
    heat_max = 0
    for week in range(HEAT_WEEKS):
        sunday = first_sunday + timedelta(days=7 * week)
        cells = []
        # 月标签口径同 DSH heatmap.tsx:91-93：首周 / 跨月 / 周内首日是 1 号时开标签，
        # 文案取「周六」那天的月份（column[6]），不是周日——取周日会让跨月那周和下一周重名
        saturday = sunday + timedelta(days=6)
        opens = (week == 0 or sunday.month != saturday.month or sunday.day == 1)
        month_label = _t(f'{saturday.month} 月') if opens else ''
        for offset in range(7):
            day = sunday + timedelta(days=offset)
            value = heat_counts.get(day, 0)
            if day > today:
                cells.append({'key': day.isoformat(), 'future': True,
                              'level': 0, 'value': 0})
                continue
            if value <= 0 or peak <= 0:
                level = 0
            else:
                ratio = value / peak
                level = 1
                for step in HEAT_LEVELS:
                    if ratio > step:
                        level += 1
            heat_max = max(heat_max, value)
            cells.append({'key': day.isoformat(), 'future': False,
                          'level': level, 'value': value})
        heat_cols.append({'cells': cells, 'month': month_label})
    # 星期行标签：DSH 只标一 / 三 / 五，其余留空保证七行对齐
    weekday_names = {1: '一', 3: '三', 5: '五'}
    heat_weeks = [{'label': _t(weekday_names[row]) if row in weekday_names else '',
                   'index': row} for row in range(7)]

    return {
        'usage7': usage7,
        'usage7_ticks': usage7_ticks,
        'usage7_max_submitted': max_submitted,
        'usage7_max_finished': max_finished,
        'heat_cols': heat_cols,
        'heat_max': heat_max,
        'heat_weeks': heat_weeks,
    }


def build_dashboard(*, user, is_admin, enabled_names, range_key, chart,
                    pending_approvals, attendance_today, range_base='/'):
    """组装看板上下文（cards / trend / pie / dept / range_links）。

    v2.1.9：`range_base` 由调用方给「当前页 + 其余查询参数」，范围切换才留得住页面。
    此前这里写死 `/?range=<key>`：在 /dashboard/ 点「本周」会跳到首页对话面板，
    在首页「看板」面板里点又会丢掉 `panel=dashboard` —— 也就是用户看到的「切换失效」。
    """
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
        try:
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
            # 没有审批权限的账号看不到「待我审批」，用「我的待处理」补第 5 张 KPI：
            # 口径是本人提交、当前仍在 pending 的单据（实时，不受 range 影响）
            my_pending = Approval.objects.filter(applicant=user, status='pending').count()
            # 顺带给同一账号的「部门签到」位补一块等价内容：本人单据按状态分档
            my_rows = {row['status']: row['n'] for row in
                       Approval.objects.filter(applicant=user)
                       .values('status').annotate(n=Count('id'))}
            status_rows = [
                {'label': _t(label), 'count': my_rows.get(key, 0)}
                for key, label in (('pending', '审批中'), ('approved', '已通过'),
                                   ('rejected', '已驳回'))
            ]
            cards['mine'] = {'pending': my_pending, 'total': flow_total,
                             'link': '/plugins/approval/',
                             'status': status_rows,
                             'status_max': max((row['count'] for row in status_rows), default=0)}
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
        except (OperationalError, ProgrammingError):
            _degraded('approval')

    if Attendance is not None and 'attendance' in enabled_names:
        try:
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
        except (OperationalError, ProgrammingError):
            _degraded('attendance')

    # 插件运行状态（管理员）
    if is_admin:
        enabled_count, total_plugins = plugin_counts()
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
            try:
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
            except (OperationalError, ProgrammingError):
                _degraded('blockchain')
                pie = None

        # 组织人员柱状图：部门人数 / 今日签到 / 待审批（按审批人部门）
        Department = _model('user', 'Department')
        if Department is not None and 'user' in enabled_names:
            try:
                departments = list(
                    Department.objects.filter(is_active=True)
                    .annotate(headcount=Count('members', filter=Q(members__is_active=True)))
                    .order_by('-headcount', 'name')[:10])
                dept_ids = [item.id for item in departments]
                today_checked = {}
                if Attendance is not None and 'attendance' in enabled_names:
                    today_checked = {
                        row['user__department_id']: row['n']
                        for row in Attendance.objects.filter(
                            date=now.date(), check_in__isnull=False,
                            user__department_id__in=dept_ids)
                        .values('user__department_id')
                        .annotate(n=Count('user', distinct=True))
                    }
                pending_map = {}
                if Approval is not None and 'approval' in enabled_names:
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
                    'total': Department.objects.filter(is_active=True).count(),
                    'max': max((item['headcount'] for item in rows), default=0),
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
            except (OperationalError, ProgrammingError):
                _degraded('structure')
                dept = None

    range_links = [{
        'key': key,
        'label': _t(RANGE_LABELS[key]),
        'url': f'{range_base}{"&" if "?" in range_base else "?"}range={key}',
        'active': key == range_key,
    } for key in RANGE_KEYS]

    # dsh-context 版式（近 7 天双柱 + 8 周热力）用的两段时间序列，与 range 无关
    insight = _build_insight(
        user=user, is_admin=is_admin, enabled_names=enabled_names, now=now)
    insight['composition'] = _composition_of(cards.get('flow'))

    return {
        'range_key': range_key,
        'range_label': range_label,
        'range_links': range_links,
        'cards': cards,
        'trend': trend,
        'pie': pie,
        'dept': dept,
        'insight': insight,
    }
