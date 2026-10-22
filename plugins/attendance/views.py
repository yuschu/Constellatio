"""attendance 插件视图：考勤看板 + 打卡 + 签到详情（管理岗） + 补卡。"""

from datetime import datetime, time as dtime

from django.apps import apps as dj_apps
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from plugin_host.permissions import require_perm
from plugin_host.signals import attendance_checked

from .models import Attendance

# 迟到口径：签到时间晚于当日 09:00（与模型 WORK_START 一致）
LATE_TIME = dtime(9, 0)


@login_required
def attendance_dashboard(request):
    """考勤看板：今日状态 + 本月出勤/迟到统计（全员可用）。"""
    today = timezone.localdate()
    now = timezone.localtime()
    record = Attendance.objects.filter(user=request.user, date=today).first()
    month_start = today.replace(day=1)
    month_records = Attendance.objects.filter(
        user=request.user, date__gte=month_start)
    late = month_records.filter(status=Attendance.Status.LATE).count()

    return render(request, 'attendance/attendance_dashboard.html', {
        'record': record,
        'today': today,
        'now': now,
        'month_days': month_records.count(),
        'month_late': late,
        'sign_types': Attendance.SignType.choices,
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
