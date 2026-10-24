"""attendance 插件视图：考勤看板 + 打卡 + 签到详情（管理岗） + 补卡 + 月度统计。"""

import calendar
from datetime import date, datetime, time as dtime, timedelta

from django.apps import apps as dj_apps
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _

from plugin_host.charts import get_active_chart
from plugin_host.permissions import require_perm
from plugin_host.signals import attendance_checked

from .models import Attendance

# 迟到口径：签到时间晚于当日 09:00（与模型 WORK_START 一致）
LATE_TIME = dtime(9, 0)

# 月度统计的月份参数格式（?month=YYYY-MM）
MONTH_FORMAT = '%Y-%m'


@login_required
def attendance_dashboard(request):
    """考勤看板：今日状态 + 本月出勤/迟到统计 + 本月图表（全员可用）。"""
    today = timezone.localdate()
    now = timezone.localtime()
    record = Attendance.objects.filter(user=request.user, date=today).first()
    month_start = today.replace(day=1)
    month_records = Attendance.objects.filter(
        user=request.user, date__gte=month_start)
    late = month_records.filter(status=Attendance.Status.LATE).count()

    month_stats, _rows = _month_stats(month_start, user=request.user)
    chart = get_active_chart()
    attendance_chart = None
    if chart is not None:
        attendance_chart = chart.payload(
            kind='cartesian',
            categories=month_stats['dates'],
            series=[{'name': item['label'], 'data': item['data'], 'type': 'bar'}
                    for item in month_stats['series']],
        )
    status_totals = [
        {'label': item['label'], 'count': sum(item['data'])}
        for item in month_stats['series']
    ]

    return render(request, 'attendance/attendance_dashboard.html', {
        'record': record,
        'today': today,
        'now': now,
        'month_days': month_records.count(),
        'month_late': late,
        'sign_types': Attendance.SignType.choices,
        'attendance_chart': attendance_chart,
        'status_totals': status_totals,
    })


@login_required
def attendance_check(request):
    """打卡：action=in 签到 / action=out 签退（全员基线权限）。"""
    if not request.user.has_perm('attendance_check'):
        return redirect('index')
    if request.method == 'POST':
        today = timezone.localdate()
        record, _ = Attendance.objects.get_or_create(user=request.user, date=today)
        now = timezone.localtime()
        sign_type = request.POST.get('sign_type')
        if sign_type in Attendance.SignType.values and not record.check_in:
            record.sign_type = sign_type
        if request.POST.get('action') == 'in' and not record.check_in:
            record.check_in = now
        elif request.POST.get('action') == 'out' and not record.check_out:
            record.check_out = now
        record.save()
        attendance_checked.send(
            sender=record.__class__, user_id=request.user.id, date=str(record.date))
    return redirect('attendance:attendance_dashboard')


def _departments():
    """跨插件零 import：动态取 user.Department；插件停用时降级为空。"""
    try:
        Department = dj_apps.get_model('user', 'Department')
    except LookupError:
        return []
    return Department.objects.filter(is_active=True).order_by('name')


def _employees():
    try:
        User = dj_apps.get_model('user', 'User')
    except LookupError:
        return []
    return User.objects.filter(is_active=True).order_by('last_name', 'username')


def _parse_aware(value):
    """datetime-local 字符串 → 时区感知 datetime；非法返回 None。"""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _combine(day, value):
    """date + HH:MM → 时区感知 datetime；空值返回 None。"""
    if not value:
        return None
    try:
        clock = dtime.fromisoformat(value)
    except ValueError:
        return None
    return timezone.make_aware(datetime.combine(day, clock))


def _parse_month(value):
    """'YYYY-MM' → 当月 1 日；格式非法抛 ValueError。"""
    parsed = datetime.strptime(value, MONTH_FORMAT)
    return date(parsed.year, parsed.month, 1)


def _month_days(first):
    """当月逐日 date 列表（含 1 日到月末）。"""
    last_day = calendar.monthrange(first.year, first.month)[1]
    return [first + timedelta(days=offset) for offset in range(last_day)]


def _month_stats(first, department_id=None, user=None):
    """月度统计：与签到详情同源（Attendance），按日 / 按状态 / 按人聚合。

    `user` 限定个人（考勤看板），`department_id` 限定部门（管理看板）；
    返回 (stats, table_rows)：
    - stats 是 JSON 契约（见 docs/plugin-dev-v16.md §2.5），供 /stats/ 与图表使用；
    - table_rows 是只含有记录日期的降级表格行（管理页无图表时展示）。
    """
    days = _month_days(first)
    records = Attendance.objects.filter(date__range=(days[0], days[-1]))
    if department_id:
        records = records.filter(user__department_id=department_id)
    if user is not None:
        records = records.filter(user=user)

    per_day = {
        (row['date'], row['status']): row['n']
        for row in records.values('date', 'status').annotate(n=Count('id'))
    }
    series = []
    totals = {}
    for status in Attendance.Status:
        data = [per_day.get((day, status.value), 0) for day in days]
        series.append({'key': status.value, 'label': _(status.label), 'data': data})
        totals[status.value] = sum(data)

    per_user = {}
    for row in records.values(
            'user__username', 'user__last_name', 'status').annotate(n=Count('id')):
        bucket = per_user.setdefault(row['user__username'], {
            'username': row['user__username'],
            'name': row['user__last_name'] or row['user__username'],
            **{status.value: 0 for status in Attendance.Status},
        })
        bucket[row['status']] = row['n']
    users = sorted(
        per_user.values(),
        key=lambda item: (-sum(item[status.value] for status in Attendance.Status),
                          item['username']),
    )

    totals['records'] = sum(totals[status.value] for status in Attendance.Status)
    table_rows = []
    for index, day in enumerate(days):
        counts = {item['key']: item['data'][index] for item in series}
        total = sum(counts.values())
        if total:
            table_rows.append({'date': day.strftime('%m-%d'), 'total': total, **counts})

    stats = {
        'month': first.strftime(MONTH_FORMAT),
        'range': {'start': days[0].isoformat(), 'end': days[-1].isoformat()},
        'dates': [day.strftime('%m-%d') for day in days],
        'series': series,
        'totals': totals,
        'users': users,
    }
    return stats, table_rows


@require_perm('attendance_report_view')
def attendance_records(request):
    """签到详情（管理岗）：时间范围 / 状态 / 类型 / 部门 / 姓名筛选 + 汇总 + 分页。"""
    now = timezone.localtime()
    default_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = _parse_aware(request.GET.get('start')) or default_start
    end = _parse_aware(request.GET.get('end')) or now
    if end < start:
        start, end = end, start

    records = Attendance.objects.filter(date__range=(start.date(), end.date()))
    records = records.filter(
        Q(check_in__range=(start, end))
        | Q(check_in__isnull=True, date__range=(start.date(), end.date())))
    records = records.select_related('user', 'user__department')

    department_id = (request.GET.get('department') or '').strip()
    keyword = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    sign_type = (request.GET.get('sign_type') or '').strip()
    if department_id.isdigit():
        records = records.filter(user__department_id=int(department_id))
    if keyword:
        records = records.filter(
            Q(user__last_name__icontains=keyword) | Q(user__username__icontains=keyword))
    if status in Attendance.Status.values:
        records = records.filter(status=status)
    if sign_type in Attendance.SignType.values:
        records = records.filter(sign_type=sign_type)
    records = records.order_by('-date', 'user__last_name', 'user__username')

    total = records.count()
    user_count = records.values('user_id').distinct().count()
    late_count = records.filter(status=Attendance.Status.LATE).count()
    missing_count = records.filter(status=Attendance.Status.MISSING).count()

    # v1.6 月度看板：月份与部门跟随签到详情筛选；图表停用时表格降级
    month_param = (request.GET.get('month') or '').strip()
    try:
        month_first = _parse_month(month_param) if month_param else now.date().replace(day=1)
    except ValueError:
        month_first = now.date().replace(day=1)
    stats_department_id = int(department_id) if department_id.isdigit() else None
    month_stats, chart_rows = _month_stats(month_first, stats_department_id)

    page_obj = Paginator(records, 25).get_page(request.GET.get('page'))

    return render(request, 'attendance/attendance_records.html', {
        'start_value': start.strftime('%Y-%m-%dT%H:%M'),
        'end_value': end.strftime('%Y-%m-%dT%H:%M'),
        'start': start,
        'end': end,
        'rows': page_obj,
        'page_obj': page_obj,
        'total': total,
        'user_count': user_count,
        'late_count': late_count,
        'missing_count': missing_count,
        'departments': _departments(),
        'employees': _employees(),
        'department_id': department_id,
        'keyword': keyword,
        'status': status,
        'sign_type': sign_type,
        'status_choices': Attendance.Status.choices,
        'sign_types': Attendance.SignType.choices,
        # 月度看板（v1.6）：chart 为 None 时模板只渲染表格
        'chart': get_active_chart(),
        'month_value': month_first.strftime(MONTH_FORMAT),
        'chart_rows': chart_rows,
        'chart_totals': month_stats['totals'],
    })



@require_perm('attendance_report_view')
def attendance_makeup(request):
    """补卡（管理岗）：为指定员工指定日期登记补卡记录。"""
    if request.method == 'POST':
        User = dj_apps.get_model('user', 'User')
        target = User.objects.filter(pk=request.POST.get('user')).first()
        day = parse_date(request.POST.get('date') or '') or timezone.localdate()
        if target is not None:
            record, _ = Attendance.objects.get_or_create(user=target, date=day)
            sign_type = request.POST.get('sign_type')
            if sign_type in Attendance.SignType.values:
                record.sign_type = sign_type
            record.check_in = _combine(day, request.POST.get('check_in'))
            record.check_out = _combine(day, request.POST.get('check_out'))
            record.is_makeup = True
            record.save()
    return redirect('attendance:attendance_records')


@require_perm('attendance_report_view')
def attendance_stats(request):
    """月度统计 JSON（v1.6）：图表数据源；与签到详情同权限、同口径。

    `?month=YYYY-MM`（缺省当前月，非法 400）+ 可选 `department=<id>`；
    图表引擎可用时附带 `payload`（engine + option），停用时为 null。
    """
    month_param = (request.GET.get('month') or '').strip()
    if month_param:
        try:
            month_first = _parse_month(month_param)
        except ValueError:
            return JsonResponse({
                'error': 'invalid_month',
                'message': _('月份格式应为 YYYY-MM'),
            }, status=400)
    else:
        month_first = timezone.localdate().replace(day=1)

    department_id = (request.GET.get('department') or '').strip()
    department_id = int(department_id) if department_id.isdigit() else None

    stats, _table_rows = _month_stats(month_first, department_id)
    chart = get_active_chart()
    if chart is None:
        stats['payload'] = None
    else:
        stats['payload'] = chart.payload(
            categories=stats['dates'],
            series=[{'key': item['key'], 'name': item['label'], 'data': item['data']}
                    for item in stats['series']],
        )
    return JsonResponse(stats)
