"""attendance 插件业务逻辑（v1.7.14）：状态判定 / 打卡 / 补卡。

三个函数都不读 `request`，可在 `manage.py shell` 里用显式参数直接调用：

    from plugins.attendance import services
    services.judge_status(is_makeup=False, check_in=..., check_out=..., rule=None)
    services.check(user, action='in')                     # 打卡
    services.register_makeup(operator, target_user, date, sign_type='internal', ...)

锁与事务边界（v1.7.x 防丢更新）原样保留：两条写路径都是
`transaction.atomic()` 包住 `select_for_update()` 取行 → 只 `save(update_fields=...)`。
搬家时没有放宽任何一处锁——这是 review 明确要求「不得因为搬家降级为无锁」的点。
"""

from django.db import transaction
from django.utils import timezone

from .models import Attendance, AttendanceRule


def judge_status(*, is_makeup, check_in, check_out, rule=None):
    """考勤状态判定（纯函数，无副作用、不读 request、不查库——除非传入 rule=None）。

    口径：补卡 > 缺卡 > 迟到 > 早退 > 正常。
    传入 `rule` 时完全不碰数据库，适合在 shell / 单测里验证边界。
    """
    if is_makeup:
        return Attendance.Status.MAKEUP
    if not check_in:
        return Attendance.Status.MISSING
    rule = rule or AttendanceRule.get_solo()
    if timezone.localtime(check_in).time() > rule.late_threshold():
        return Attendance.Status.LATE
    if not check_out:
        return Attendance.Status.MISSING
    if timezone.localtime(check_out).time() < rule.early_threshold():
        return Attendance.Status.EARLY
    return Attendance.Status.NORMAL


def check(user, *, action, sign_type=None, now=None):
    """打卡：action=in 签到 / action=out 签退；返回落库后的记录。

    锁内重读当天记录、只把本次真正改动的字段写回：签退不会清掉并发签到写入的 check_in，
    重复打卡也只落在同一行（`unique_together` 保证）。
    """
    today = timezone.localdate()
    now = now or timezone.now()
    record = None
    with transaction.atomic():
        record, _ = Attendance.objects.get_or_create(user=user, date=today)
        record = Attendance.objects.select_for_update().get(pk=record.pk)
        changed = []
        if (sign_type in Attendance.SignType.values
                and record.check_in is None
                and record.sign_type != sign_type):
            record.sign_type = sign_type
            changed.append('sign_type')
        if action == 'in' and record.check_in is None:
            record.check_in = now
            changed.append('check_in')
        elif action == 'out' and record.check_out is None:
            record.check_out = now
            changed.append('check_out')
        if changed:
            # model.save() 由打卡时间重算 status（补卡 > 缺卡 > 迟到 > 早退 > 正常）
            record.save(update_fields=changed + ['status', 'updated_at'])
    return record


def register_makeup(operator, target, day, *, sign_type=None, check_in=None, check_out=None):
    """补卡登记（管理岗）：为指定员工指定日期写入补卡记录，返回落库后的记录。

    `operator` 只用于留痕/日志语义，鉴权由调用方（视图的 `require_perm`）负责；
    行锁范围与原实现一致，避免与员工并发打卡互相覆盖。
    """
    with transaction.atomic():
        record, _ = Attendance.objects.get_or_create(user=target, date=day)
        record = Attendance.objects.select_for_update().get(pk=record.pk)
        if sign_type in Attendance.SignType.values:
            record.sign_type = sign_type
        record.check_in = check_in
        record.check_out = check_out
        record.is_makeup = True
        # status 由 model.save() 重算（is_makeup=True → 补卡），保持既有口径
        record.save(update_fields=[
            'sign_type', 'check_in', 'check_out', 'is_makeup', 'status', 'updated_at'])
    return record
