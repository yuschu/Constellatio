"""attendance 插件视图：考勤看板 + 打卡 + 签到详情（管理岗） + 补卡 + 月度统计。"""

import calendar
from datetime import date, datetime, timedelta
from datetime import time as dtime

from django.apps import apps as dj_apps
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from plugin_host.charts import get_active_chart
from plugin_host.exceptions import ObjectPermissionDenied
from plugin_host.pagination import paginate
from plugin_host.permissions import require_perm
from plugin_host.signals import attendance_checked

from . import services
from .forms import AttendanceRuleForm
from .models import Attendance, AttendanceRule

# 月度统计的月份参数格式（?month=YYYY-MM）
MONTH_FORMAT = '%Y-%m'


def _now():
    """当前时区感知时间（单独抽出便于测试替换打卡时刻）。"""
    return timezone.localtime()


# v2.2.2：Jibble 形态的工时口径只用这一处——时长为「签到 → 签退（或此刻）」。
WEEK_LABELS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def _worked_hours(record, now):
    """一条考勤记录已工作的时长（小时，float）；未签到 / 未来日期返回 0。"""
    if record is None or record.check_in is None:
        return 0.0
    end = record.check_out or now
    if end < record.check_in:
        return 0.0
    return (end - record.check_in).total_seconds() / 3600.0


def _hours_text(hours):
    """小时数 → Jibble 的 `5h 12m` 写法（分钟四舍五入）。"""
    total = int(round(max(hours, 0.0) * 60))
    return f'{total // 60}h {total % 60:02d}m'


def _week_bars(user, today, now):
    """本周（周一为首日）逐日工时柱：Jibble「Tracked hours」那一块的取数。"""
    start = today - timedelta(days=today.isoweekday() - 1)
    bars = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        record = Attendance.objects.filter(user=user, date=day).first()
        hours = _worked_hours(record, now) if day <= today else 0.0
        bars.append({
            'day': day,
            'label': _(WEEK_LABELS[offset]),
            'hours': hours,
            'hours_text': _hours_text(hours),
            'is_today': day == today,
            'future': day > today,
        })
    # 柱高按「至少 8 小时」定标：正常一天不会把柱子挤满，短工时也不会被抹平
    peak = max([bar['hours'] for bar in bars] + [8.0])
    for bar in bars:
        bar['percent'] = round(bar['hours'] / peak * 100, 1) if peak else 0.0
    total = sum(bar['hours'] for bar in bars)
    return {'start': start, 'bars': bars, 'total': total, 'total_text': _hours_text(total)}


def _employee_count():
    """在职人数（跨插件动态取 user.User，插件停用时降级为 0）。"""
    try:
        User = dj_apps.get_model('user', 'User')
    except LookupError:
        return 0
    return User.objects.filter(is_active=True).count()


def _today_team(today, now):
    """今日在班情况：Jibble「Who's in」那一块。

    v2.2.5：名单对全员可见（谁在班属于公共信息），不再按
    `attendance_report_view` 收口；聚合数字与名单同一口径。
    """
    records = list(
        Attendance.objects.filter(date=today)
        .select_related('user', 'user__department')
        .order_by('check_in', 'user__username'))
    signed = [item for item in records if item.check_in is not None]
    done = [item for item in signed if item.check_out is not None]
    late = [item for item in records if item.status == Attendance.Status.LATE]
    total = _employee_count()
    missing = max(total - len(signed), 0) if total else 0

    rows = []
    for record in signed[:8]:
        name = record.user.last_name or record.user.username
        rows.append({
            'name': name,
            'initial': (name[:1] or '?').upper(),
            'dept': record.user.department.name if record.user.department else '',
            'check_in': timezone.localtime(record.check_in).strftime('%H:%M'),
            'check_out': (timezone.localtime(record.check_out).strftime('%H:%M')
                          if record.check_out else ''),
            'hours_text': _hours_text(_worked_hours(record, now)),
            'status_label': _(record.get_status_display()),
            'done': record.check_out is not None,
        })

    return {
        'rows': rows,
        'signed': len(signed),
        'done': len(done),
        'late': len(late),
        'missing': missing,
        'total': total,
        'signed_percent': round(len(signed) / total * 100) if total else 0,
    }


def _recent_rows(user, limit=5):
    """我的最近打卡（Jibble 的 activity log）：只取本人记录。"""
    rows = []
    for record in Attendance.objects.filter(user=user).order_by('-date')[:limit]:
        rows.append({
            'date': record.date.strftime('%m-%d'),
            'weekday': _(WEEK_LABELS[record.date.isoweekday() - 1]),
            'check_in': (timezone.localtime(record.check_in).strftime('%H:%M')
                         if record.check_in else ''),
            'check_out': (timezone.localtime(record.check_out).strftime('%H:%M')
                          if record.check_out else ''),
            'hours_text': _hours_text(_worked_hours(record, _now())),
            'status_label': _(record.get_status_display()),
            'status': record.status,
            'sign_type_label': _(record.get_sign_type_display()),
        })
    return rows


@login_required
def attendance_dashboard(request):
    """考勤看板：今日状态 + 本月出勤/迟到统计 + 本月图表（全员可用）。"""
    return render(
        request, 'attendance/attendance_dashboard.html',
        attendance_context(request))


def attendance_context(request):
    """考勤看板上下文（v2.1.0 抽出）：业务页与首页「考勤」面板共用。

    打卡表单会 POST 到 `attendance:attendance_check`，成功与否都回业务页；
    首页面板只是同一份正文的另一个落点，所以上下文必须完全一致。
    """
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
    rule = AttendanceRule.get_solo()
    today_hours = _worked_hours(record, now)
    # 月内工时合计：month_records 已在上面查过，这里只做内存累加，不再多打一轮库
    month_hours = sum(_worked_hours(item, now) for item in month_records)
    week = _week_bars(request.user, today, now)
    team = _today_team(today, now)
    recent_rows = _recent_rows(request.user)
    if record is None:
        status_key = 'idle'
        status_label = _('未打卡')
    elif record.check_out:
        status_key = 'done'
        status_label = _('已签退')
    else:
        status_key = 'active'
        status_label = _('已签到')

    return {
        'record': record,
        'today': today,
        'today_text': date_format(today),
        'now': now,
        'month_days': month_records.count(),
        'month_late': late,
        'month_hours_text': _hours_text(month_hours),
        'today_hours_text': _hours_text(today_hours),
        'status_key': status_key,
        'status_label': status_label,
        'week': week,
        'team': team,
        'recent_rows': recent_rows,
        'can_view_report': request.user.has_perm('attendance.attendance_report_view'),
        'sign_types': Attendance.SignType.choices,
        'attendance_chart': attendance_chart,
        'status_totals': status_totals,
        # v1.7.2：今日状态卡展示当前考勤口径（迟到 / 早退判定阈值）
        'rule': rule,
        'rule_start': rule.work_start.strftime('%H:%M'),
        'rule_end': rule.work_end.strftime('%H:%M'),
        'rule_late': rule.late_threshold().strftime('%H:%M'),
        'rule_early': rule.early_threshold().strftime('%H:%M'),
        # v2.1.2：「考勤规则」是考勤的二级页。业务页按 URL 直链打开整页；
        # 首页面板会在 assistant 里把它改写成 `/?panel=attendance&sub=rules`。
        'rules_entry_url': reverse('attendance:attendance_rules'),
    }


@login_required
def attendance_check(request):
    """打卡：action=in 签到 / action=out 签退（全员基线权限）。

    v1.7.14：锁内重读与字段重写搬到 `services.check`，视图只取参数、调用、发信号。
    """
    if not request.user.has_perm('attendance_check'):
        # v1.7.11：手写的 has_perm 也要与 require_perm 同口径（原 302 回工作台）
        raise ObjectPermissionDenied('无权访问该功能')
    if request.method == 'POST':
        # `now=_now()`：既有测试通过替换 views._now 控制打卡时刻（断言一条不改的前提）
        record = services.check(
            request.user,
            action=request.POST.get('action'),
            sign_type=request.POST.get('sign_type'),
            now=_now())
        attendance_checked.send(
            sender=record.__class__, user_id=request.user.id, date=str(record.date))
    return redirect(_return_url(request) or 'attendance:attendance_dashboard')


def _return_url(request):
    """打卡后回到哪：v2.1.0 起首页也能承载考勤面板，表单带 `next` 就回那一页。"""
    next_url = request.POST.get('next') or ''
    if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return next_url
    return None


def save_rules(request):
    """校验并保存考勤规则：返回 ``(form, response)``。

    保存成功时第二个元素是 PRG 响应（回 `next` / 本页并带 `saved=1`）；
    校验失败时第二个元素是 ``None``，宿主（业务页或首页面板）就地渲染错误。
    两个宿主共用这一份校验，避免出现「面板里能填、业务页里不校验」这类双口径。
    """
    rule = AttendanceRule.get_solo()
    # 用独立实例绑定表单：ModelForm 会把校验后的字段原地写回 instance，
    # 直接传 get_solo() 的缓存对象会让非法输入污染进程内缓存。
    form = AttendanceRuleForm(
        request.POST, instance=AttendanceRule.objects.get(pk=rule.pk))
    if not form.is_valid():
        return form, None
    rule = form.save(commit=False)
    rule.updated_by = request.user
    rule.save()
    target = _return_url(request) or reverse('attendance:attendance_rules')
    sep = '&' if '?' in target else '?'
    return form, redirect(f'{target}{sep}saved=1')


@require_perm('attendance_rule_manage')
def attendance_rules(request):
    """考勤规则设置（单例）：上下班时间 / 迟到早退宽限 / 工作日 / 补卡回溯。

    保存成功走 PRG（redirect 回本页并带 ``?saved=1``），页面内展示成功标识，
    与项目现有「表单页 + 内联提示」的风格一致（未引入 messages 渲染）。

    v2.1.2：本页既是独立深链，也是首页「考勤」面板设置弹层里的同一块正文
    （`/?panel=attendance&sub=rules` 打开弹层，弹层内容复用 `_rules_panel.html`）。
    面板里的表单把 `next` 指回面板 URL，保存成功后 PRG 回面板并带 `saved=1`；
    校验/保存本身在 `save_rules()`，首页 POST 时由 home 直接调用同一份。
    """
    rule = AttendanceRule.get_solo()
    saved = request.GET.get('saved') == '1'
    if request.method == 'POST':
        form, response = save_rules(request)
        if response is not None:
            return response
    else:
        form = AttendanceRuleForm(instance=rule)

    context = rules_context(request, rule=rule, form=form, saved=saved)
    context['rules_close_url'] = reverse('attendance:attendance_dashboard')
    return render(request, 'attendance/attendance_rules.html', context)


def rules_context(request, rule=None, form=None, saved=None):
    """考勤规则页的上下文字段（业务页与首页面板二级页共用）。

    只做只读装配：保存逻辑仍留在 `attendance_rules` 视图里，
    面板二级页拿到的就是同一份表单实例与阈值口径。
    """
    rule = rule if rule is not None else AttendanceRule.get_solo()
    form = form if form is not None else AttendanceRuleForm(instance=rule)
    saved = request.GET.get('saved') == '1' if saved is None else saved
    return {
        'form': form,
        'rule': rule,
        'saved': saved,
        'rule_late': rule.late_threshold().strftime('%H:%M'),
        'rule_early': rule.early_threshold().strftime('%H:%M'),
    }


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

    page_obj = paginate(request, records)

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
    """补卡（管理岗）：为指定员工指定日期登记补卡记录。

    v1.7.14：落库与行锁在 `services.register_makeup`；视图只做参数提取（含跨插件取用户）。
    """
    if request.method == 'POST':
        User = dj_apps.get_model('user', 'User')
        target = User.objects.filter(pk=request.POST.get('user')).first()
        if target is not None:
            day = parse_date(request.POST.get('date') or '') or timezone.localdate()
            services.register_makeup(
                request.user, target, day,
                sign_type=request.POST.get('sign_type'),
                check_in=_combine(day, request.POST.get('check_in')),
                check_out=_combine(day, request.POST.get('check_out')))
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
                # v1.7.5：JSON 错误体统一为 {code, message}（前端无消费方，直接切换）
                'code': 'invalid_month',
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
