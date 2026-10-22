"""attendance 插件视图：考勤看板 + 打卡 + 签到详情（管理岗）。"""

import calendar
from datetime import date, time as dtime

from django.apps import apps as dj_apps
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from plugin_host.permissions import require_perm
from plugin_host.signals import attendance_checked

from .models import Attendance

# 迟到口径：签到时间晚于当日 09:00（与看板一致）
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
    late = month_records.filter(check_in__time__gt=LATE_TIME).count()

    return render(request, 'attendance/attendance_dashboard.html', {
        'record': record,
        'today': today,
        'now': now,
        'month_days': month_records.count(),
        'month_late': late,
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
        if request.POST.get('action') == 'in' and not record.check_in:
            record.check_in = now
        elif request.POST.get('action') == 'out' and not record.check_out:
            record.check_out = now
        record.save()
        attendance_checked.send(
            sender=record.__class__, user_id=request.user.id, date=str(record.date))
    return redirect('attendance:attendance_dashboard')


def _month_range(month_raw):
    """解析 YYYY-MM；非法输入回退当月。返回 (year, month, start, end)。"""
    today = timezone.localdate()
    try:
        year, month = (int(part) for part in month_raw.split('-')[:2])
        start = date(year, month, 1)
    except (ValueError, TypeError):
        start = today.replace(day=1)
    end = date(start.year, start.month,
               calendar.monthrange(start.year, start.month)[1])
    return start.year, start.month, start, end


def _departments():
    """跨插件零 import：动态取 user.Department；插件停用时降级为空。"""
    try:
        Department = dj_apps.get_model('user', 'Department')
    except LookupError:
        return []
    return Department.objects.filter(is_active=True).order_by('name')


@require_perm('attendance_report_view')
def attendance_records(request):
    """签到详情（管理岗）：按月份/部门/姓名筛选 + 汇总 + 分页。"""
    month_raw = request.GET.get('month') or ''
    year, month, start, end = _month_range(month_raw)

    records = Attendance.objects.filter(date__range=(start, end)).select_related(
        'user', 'user__department')
    department_id = (request.GET.get('department') or '').strip()
    keyword = (request.GET.get('q') or '').strip()
    if department_id.isdigit():
        records = records.filter(user__department_id=int(department_id))
    if keyword:
        records = records.filter(
            Q(user__last_name__icontains=keyword) | Q(user__username__icontains=keyword))
    records = records.order_by('date', 'user__last_name', 'user__username')

    total = records.count()
    user_count = records.values('user_id').distinct().count()
    late_count = sum(
        1 for check_in in records.values_list('check_in', flat=True)
        if check_in and timezone.localtime(check_in).time() > LATE_TIME)

    page_obj = Paginator(records, 25).get_page(request.GET.get('page'))
    rows = [{
        'record': r,
        'late': bool(r.check_in) and timezone.localtime(r.check_in).time() > LATE_TIME,
        'missing': not r.check_in,
    } for r in page_obj]

    return render(request, 'attendance/attendance_records.html', {
        'month_value': f'{year:04d}-{month:02d}',
        'start': start,
        'end': end,
        'rows': rows,
        'page_obj': page_obj,
        'total': total,
        'user_count': user_count,
        'late_count': late_count,
        'departments': _departments(),
        'department_id': department_id,
        'keyword': keyword,
    })
