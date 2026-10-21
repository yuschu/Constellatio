"""attendance 插件视图：考勤看板 + 打卡。"""

from datetime import time as dtime

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from plugin_host.signals import attendance_checked

from .models import Attendance


@login_required
def attendance_dashboard(request):
    """考勤看板：今日状态 + 本月出勤/迟到统计。"""
    today = timezone.localdate()
    now = timezone.localtime()
    record = Attendance.objects.filter(user=request.user, date=today).first()
    month_start = today.replace(day=1)
    month_records = Attendance.objects.filter(
        user=request.user, date__gte=month_start)
    # 迟到口径：签到时间晚于当日 09:00
    late = month_records.filter(check_in__time__gt=dtime(9, 0)).count()

    return render(request, 'attendance/attendance_dashboard.html', {
        'record': record,
        'today': today,
        'now': now,
        'month_days': month_records.count(),
        'month_late': late,
    })


@login_required
def attendance_check(request):
    """打卡：action=in 签到 / action=out 签退（需 attendance_check 权限）。"""
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
