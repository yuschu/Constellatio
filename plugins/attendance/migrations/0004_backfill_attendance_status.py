"""回填既有考勤记录的签到状态（v1.5.5）。

新增 status 字段默认 missing；历史打卡记录需按打卡时间重新推导，
否则签到详情里旧记录会全部显示缺卡。
"""

from django.db import migrations
from django.utils import timezone

WORK_START_HOUR, WORK_START_MIN = 9, 0
WORK_END_HOUR, WORK_END_MIN = 18, 0


def _status(record):
    if record.is_makeup:
        return 'makeup'
    if not record.check_in:
        return 'missing'
    check_in = timezone.localtime(record.check_in)
    if (check_in.hour, check_in.minute) > (WORK_START_HOUR, WORK_START_MIN):
        return 'late'
    if not record.check_out:
        return 'missing'
    check_out = timezone.localtime(record.check_out)
    if (check_out.hour, check_out.minute) < (WORK_END_HOUR, WORK_END_MIN):
        return 'early'
    return 'normal'


def backfill_status(apps, schema_editor):
    Attendance = apps.get_model('attendance', 'Attendance')
    for record in Attendance.objects.all().iterator():
        Attendance.objects.filter(pk=record.pk).update(status=_status(record))


def noop(apps, schema_editor):
    """回滚无需处理：status 字段会随迁移 0003 一起移除。"""


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_attendance_is_makeup_attendance_sign_type_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_status, noop),
    ]
