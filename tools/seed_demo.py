#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键写入论文演示数据集（图4-7 考勤状态分布 + 图4-9 留痕来源分布）。

数据口径与 docs/thesis/build/gen_figures.py 中的绘图数据完全一致：

  图4-7  2026 年 9 月，22 个工作日，32 名用户，662 条考勤记录
         正常 470 / 迟到 131 / 早退 48 / 补卡 13，逐日分布见 NORMAL/LATE/EARLY/MAKEUP

  图4-9  留痕链共 693 条：attendance 662 / approval 24 / notice 6 / structure 1

同时补齐与两张图自洽的周边数据（论文第 5 章口径）：
  32 名用户、20 个部门、31 个角色；48 张审批单 + 64 条审批记录（24 张完结）；
  6 条公告 + 94 条已读；站内信由信号自动产生。

用法（项目根目录）：
  venv/Scripts/python.exe tools/seed_demo.py

脚本是「重置后重建」：先清空演示业务表与测试残留，再按固定随机种子重建，
因此可重复执行且每次得到同一份数据。执行前请自行备份 db.sqlite3。
"""

import os
import random
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plugin_host.settings')

# Windows 控制台默认 GBK，统一按 UTF-8 输出，避免中文/勾号打印中断
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

from plugins.approval import services as approval_services  # noqa: E402
from plugins.approval.models import (  # noqa: E402
    Approval,
    ApprovalRecord,
    ApprovalSigner,
)
from plugins.attendance.models import Attendance, AttendanceRule  # noqa: E402
from plugins.blockchain.models import BlockchainRecord  # noqa: E402
from plugins.notice.models import Announcement, AnnouncementRead  # noqa: E402
from plugins.notify.models import Notification  # noqa: E402
from plugins.structure.models import StructureRecord  # noqa: E402
from plugins.structure.services import apply_structure  # noqa: E402
from plugins.structure.template import (  # noqa: E402
    DEPARTMENTS as TEMPLATE_DEPARTMENTS,
    ROLES as TEMPLATE_ROLES,
    USERS as TEMPLATE_USERS,
)
from plugins.user.models import Department, Role  # noqa: E402
from plugin_host.signals import (  # noqa: E402
    attendance_checked,
    notice_published,
    structure_applied,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# 绘图数据（与 docs/thesis/build/gen_figures.py 的 fig4_7 / fig4_9 同源）
# ---------------------------------------------------------------------------
FIG47_DATES = ['09-01', '09-02', '09-03', '09-04', '09-07', '09-08', '09-09',
               '09-10', '09-11', '09-14', '09-15', '09-16', '09-17', '09-18',
               '09-21', '09-22', '09-23', '09-24', '09-25', '09-28', '09-29',
               '09-30']
NORMAL = [26, 20, 22, 20, 22, 17, 28, 17, 22, 22, 20, 26, 19, 21, 19, 20, 23, 22, 15, 22, 26, 21]
LATE = [2, 8, 5, 8, 6, 7, 1, 8, 9, 2, 7, 2, 9, 7, 10, 7, 5, 6, 11, 3, 4, 4]
EARLY = [2, 1, 3, 1, 2, 3, 1, 6, 1, 4, 3, 1, 3, 3, 0, 1, 1, 3, 4, 2, 1, 2]
MAKEUP = [1, 1, 0, 0, 0, 2, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1]
FIG49_COUNTS = {'attendance': 662, 'approval': 24, 'notice': 6, 'structure': 1}

RNG = random.Random(20260901)
SEPT = date(2026, 9, 1)


def workdays(year=2026, month=9):
    """2026 年 9 月的全部工作日（周一至周五）。"""
    days = []
    day = date(year, month, 1)
    while day.month == month:
        if day.isoweekday() <= 5:
            days.append(day)
        day += timezone.timedelta(days=1)
    return days


def dt_at(day, hour, minute, second=0):
    """day + 本地时刻 → 带时区 datetime（Asia/Shanghai）。"""
    return timezone.make_aware(datetime.combine(day, time(hour, minute, second)))


def minutes_to_time(value):
    return time(value // 60, value % 60)


# ---------------------------------------------------------------------------
# 1) 清空演示业务数据 + 测试残留
# ---------------------------------------------------------------------------
def reset():
    Notification.objects.all().delete()
    AnnouncementRead.objects.all().delete()
    Announcement.objects.all().delete()
    ApprovalSigner.objects.all().delete()
    ApprovalRecord.objects.all().delete()
    Approval.objects.all().delete()
    Attendance.objects.all().delete()
    BlockchainRecord.objects.all().delete()
    StructureRecord.objects.all().delete()

    # 模板之外的测试残留账号 / 部门 / 角色，保证「32 名用户 / 20 个部门 / 31 个角色」口径
    keep_users = {item[0] for item in TEMPLATE_USERS}
    User.objects.filter(is_superuser=False).exclude(username__in=keep_users).delete()
    keep_depts = {item[0] for item in TEMPLATE_DEPARTMENTS}
    Department.objects.exclude(name__in=keep_depts).delete()
    keep_roles = set(TEMPLATE_ROLES)
    Role.objects.exclude(name__in=keep_roles).delete()

    users = User.objects.count()
    depts = Department.objects.count()
    roles = Role.objects.count()
    print(f'[reset] 用户 {users} / 部门 {depts} / 角色 {roles}')


def ensure_org(admin):
    """组织模板缺失时补建（幂等），并清掉模板应用自身产生的那条架构留痕。

    空库（Docker 首次部署）与混杂库（历史测试数据）都能收敛到
    31 名模板用户 + admin、20 个部门、31 个角色的演示口径。
    """
    before = (User.objects.count(), Department.objects.count(), Role.objects.count())
    dept_created, role_created, user_created = apply_structure(
        admin, grant_manager_perms=True)
    # apply_structure 必定登记一条 StructureRecord 并上链；统一清掉后按演示口径重建 1 条
    StructureRecord.objects.all().delete()
    BlockchainRecord.objects.all().delete()

    users = User.objects.count()
    depts = Department.objects.count()
    roles = Role.objects.count()
    print(f'[org] 模板补齐 +{dept_created} 部门 / +{role_created} 角色 / '
          f'+{user_created} 用户 → 用户 {users} / 部门 {depts} / 角色 {roles}'
          f'（之前 {before[0]}/{before[1]}/{before[2]}）')
    assert users == 32, f'期望 32 名用户（admin + 31 名模板用户），实际 {users}'
    assert depts == 20, f'期望 20 个部门，实际 {depts}'
    assert roles == 31, f'期望 31 个角色，实际 {roles}'


# ---------------------------------------------------------------------------
# 2) 考勤规则回到论文口径：09:00-18:00、无宽限、周一至周五
# ---------------------------------------------------------------------------
def ensure_rule(admin):
    rule = AttendanceRule.get_solo()
    rule.work_start = time(9, 0)
    rule.work_end = time(18, 0)
    rule.late_grace_minutes = 0
    rule.early_grace_minutes = 0
    rule.workdays = '1,2,3,4,5'
    rule.makeup_window_days = 7
    rule.updated_by = admin
    rule.save()
    print(f'[rule] {rule.work_start:%H:%M}-{rule.work_end:%H:%M} 工作日 {rule.workdays}')


# ---------------------------------------------------------------------------
# 3) 组织架构应用留痕：1 条（图4-9 的 structure 来源）
# ---------------------------------------------------------------------------
def seed_structure(admin):
    applied_at = dt_at(SEPT, 9, 0)
    record = StructureRecord.objects.create(
        applied_by=admin, dept_created=20, role_created=31, user_created=31,
        grant_manager_perms=True)
    StructureRecord.objects.filter(pk=record.pk).update(applied_at=applied_at)
    chain = BlockchainRecord.append(
        plugin='structure', action='structure_applied',
        payload='+20dept/+31role/+31user', operator=admin)
    BlockchainRecord.objects.filter(pk=chain.pk).update(created_at=applied_at)
    print('[structure] 应用留痕 1 条')


# ---------------------------------------------------------------------------
# 4) 审批：48 张单 / 64 条记录 / 24 张完结（approval 来源 24 条）
# ---------------------------------------------------------------------------
APPROVAL_BLUEPRINT = {
    'leave': ('请假申请', '因个人事务申请请假，望批准。', None),
    'expense': ('差旅报销', '出差往返交通与住宿费用报销。', True),
    'seal': ('用章申请', '项目合同签署用章，附件已上传。', None),
    'outing': ('外出申请', '客户现场支持，需外出办理。', None),
    'overtime': ('加班申请', '版本发布需要，周末加班处理。', None),
    'comp': ('调休申请', '加班调休，申请休息一天。', None),
}
# 48 张单：8 草稿（0 记录）+ 16 待审批（16 记录）+ 18 通过 + 6 驳回
# = 48 张单 / 64 条记录 / 24 张完结
OUTCOMES = ['draft'] * 8 + ['pending'] * 16 + ['approved'] * 18 + ['rejected'] * 6


def seed_approvals(admin):
    staff = list(User.objects.filter(is_superuser=False).order_by('id'))
    assert len(staff) == 31, f'模板用户应为 31 人，实际 {len(staff)}'
    days = workdays()

    created = []
    for i, outcome in enumerate(OUTCOMES):
        kind = list(APPROVAL_BLUEPRINT)[i % len(APPROVAL_BLUEPRINT)]
        # 用章通过会追加一条 e_seal 留痕，为保证 64 条记录口径，完结单不用用章
        if outcome in ('approved', 'rejected') and kind == 'seal':
            kind = 'outing'
        label, content, needs_amount = APPROVAL_BLUEPRINT[kind]
        applicant = staff[(i * 5) % len(staff)]
        approver = applicant.leader or admin
        name = applicant.last_name or applicant.username
        day = days[(i * 7) % len(days)]
        created_at = dt_at(day, 9 + i % 8, (i * 13) % 60)

        approval = Approval.objects.create(
            approval_type=kind,
            title=f'{name}的{label}（{day.month}月{day.day}日）',
            content=content,
            amount=Decimal(f'{(i + 1) * 137}.50') if needs_amount else None,
            applicant=applicant,
            approver=approver,
            department_id=applicant.department_id,
            department_name=applicant.department.name if applicant.department_id else '',
        )
        Approval.objects.filter(pk=approval.pk).update(created_at=created_at)

        # 流转（草稿不动）
        if outcome != 'draft':
            approval_services.submit(approval, applicant, '提交审批', 'submit')
        if outcome in ('approved', 'rejected'):
            if outcome == 'approved':
                approval_services.approve(approval, approver, '同意')
            else:
                approval_services.reject(approval, approver, '材料不全/不符合规定')

        # 留痕时间回填到 9 月
        recs = list(ApprovalRecord.objects.filter(approval_id=approval.pk).order_by('id'))
        for offset, rec in enumerate(recs):
            ApprovalRecord.objects.filter(pk=rec.pk).update(
                created_at=created_at + timezone.timedelta(minutes=30 * (offset + 1)))
        approval.refresh_from_db()
        created.append(approval.pk)

    print(f'[approval] 审批单 {Approval.objects.count()} / 流转记录 {ApprovalRecord.objects.count()}')


# ---------------------------------------------------------------------------
# 5) 公告：6 条 + 94 条已读（notice 来源 6 条）
# ---------------------------------------------------------------------------
NOTICES = [
    ('关于 2026 年国庆节放假安排的通知', '10 月 1 日至 10 月 7 日放假调休，共 7 天。请各部门提前安排好工作。', True),
    ('关于第三季度绩效考核工作的通知', '第三季度绩效考核于 9 月 20 日启动，请各负责人在 9 月 30 日前完成评分与面谈。', False),
    ('新版办公系统上线公告', '新版插件化办公系统已上线，支持审批、公告、考勤与留痕查询，登录方式不变。', False),
    ('关于办公用品申领规范的通知', '办公用品统一由行政部申领，每周一、周四集中发放，请提前在系统内提交申请。', False),
    ('关于开展消防演练的通知', '9 月 26 日下午 15:00 组织全员消防演练，请按时到一楼大厅集合。', False),
    ('关于员工体检安排的通知', '本年度员工体检安排在 10 月中旬，具体时间与医院另行通知，请预留时间。', False),
]
READ_ALLOCATION = [31, 25, 18, 12, 6, 2]   # 合计 94


def seed_notices(admin):
    users = list(User.objects.order_by('id'))
    days = workdays()
    for i, (title, content, top) in enumerate(NOTICES):
        day = days[(i * 3) % len(days)]
        created_at = dt_at(day, 10, (i * 17) % 60)
        ann = Announcement.objects.create(
            title=title, content=content, publisher=admin, is_top=top)
        Announcement.objects.filter(pk=ann.pk).update(
            created_at=created_at, updated_at=created_at)
        notice_published.send(sender=Announcement, announcement_id=ann.pk)
        chain = BlockchainRecord.objects.order_by('-id').first()
        BlockchainRecord.objects.filter(pk=chain.pk).update(created_at=created_at)

        # 已读：按配额从发布人之外的用户里轮转选取
        pool = [u for u in users if u.pk != admin.pk]
        start = i * 5
        picked = [pool[(start + k) % len(pool)] for k in range(READ_ALLOCATION[i])]
        for k, reader in enumerate(picked):
            read = AnnouncementRead.objects.create(announcement=ann, user=reader)
            read_at = created_at + timezone.timedelta(hours=2, minutes=k * 7)
            AnnouncementRead.objects.filter(pk=read.pk).update(read_at=read_at)

    print(f'[notice] 公告 {Announcement.objects.count()} / 已读 {AnnouncementRead.objects.count()}')


# ---------------------------------------------------------------------------
# 6) 考勤：2026 年 9 月 22 个工作日 / 662 条（attendance 来源 662 条）
# ---------------------------------------------------------------------------
def seed_attendance():
    users = list(User.objects.order_by('id'))
    assert len(users) == 32, f'考勤用户应为 32 人，实际 {len(users)}'
    days = workdays()
    assert [d.strftime('%m-%d') for d in days] == FIG47_DATES, '9 月工作日与绘图数据不一致'

    counts = {'normal': 0, 'late': 0, 'early': 0, 'makeup': 0}
    per_day = {}

    for idx, day in enumerate(days):
        n_normal, n_late, n_early, n_makeup = (
            NORMAL[idx], LATE[idx], EARLY[idx], MAKEUP[idx])
        expected = (n_normal + n_late + n_early + n_makeup)
        assert expected <= len(users), f'{day} 记录数 {expected} 超过用户数'

        # 每天固定种子打乱用户顺序：既保证人数精确，又让缺卡人员逐日轮换
        rng = random.Random(20260900 + day.day)
        order = users[:]
        rng.shuffle(order)

        plan = [('normal', n_normal), ('late', n_late),
                ('early', n_early), ('makeup', n_makeup)]
        cursor = 0
        for status, count in plan:
            for _ in range(count):
                user = order[cursor]
                cursor += 1
                check_in, check_out = _attendance_clock(day, rng, status)
                record = Attendance(
                    user=user, date=day,
                    check_in=check_in, check_out=check_out,
                    sign_type=('external' if (cursor % 9 == 0) else 'internal'),
                    is_makeup=(status == 'makeup'))
                record.save()
                assert record.status == status, (
                    f'{user.username} {day} 期望 {status} 实得 {record.status}')
                Attendance.objects.filter(pk=record.pk).update(
                    created_at=check_in, updated_at=check_in)

                attendance_checked.send(
                    sender=Attendance, user_id=user.id, date=str(day))
                chain = BlockchainRecord.objects.order_by('-id').first()
                BlockchainRecord.objects.filter(pk=chain.pk).update(
                    created_at=check_in)
                counts[status] += 1

        per_day[day] = {
            'normal': n_normal, 'late': n_late,
            'early': n_early, 'makeup': n_makeup,
        }

    print(f'[attendance] 考勤记录 {Attendance.objects.count()} / 状态分布 {counts}')
    return counts, per_day


def _attendance_clock(day, rng, status):
    """按状态生成 (签到, 签退) 带时区时刻，保证 compute_status 推导出该状态。"""
    if status == 'normal':
        hour, minute = divmod(rng.randint(8 * 60 + 25, 8 * 60 + 59), 60)
        ci = (hour, minute)
        hour, minute = divmod(rng.randint(18 * 60, 18 * 60 + 35), 60)
        co = (hour, minute)
    elif status == 'late':
        hour, minute = divmod(rng.randint(9 * 60 + 3, 9 * 60 + 50), 60)
        ci = (hour, minute)
        hour, minute = divmod(rng.randint(18 * 60, 18 * 60 + 30), 60)
        co = (hour, minute)
    elif status == 'early':
        hour, minute = divmod(rng.randint(8 * 60 + 30, 8 * 60 + 59), 60)
        ci = (hour, minute)
        hour, minute = divmod(rng.randint(16 * 60 + 30, 17 * 60 + 58), 60)
        co = (hour, minute)
    else:  # makeup：补卡状态由 is_makeup 决定，时间不参与判定
        hour, minute = divmod(rng.randint(8 * 60 + 50, 9 * 60 + 10), 60)
        ci = (hour, minute)
        hour, minute = divmod(rng.randint(18 * 60, 18 * 60 + 10), 60)
        co = (hour, minute)
    return dt_at(day, *ci), dt_at(day, *co)


# ---------------------------------------------------------------------------
# 7) 校验：两张图的分布必须逐项吻合，哈希链必须通过
# ---------------------------------------------------------------------------
def verify():
    ok = True

    # 图4-7：逐日 + 合计
    days = workdays()
    rows = Attendance.objects.values_list('date', 'status')
    per_day = {}
    totals = {}
    for day, status in rows:
        per_day.setdefault(day, {}).setdefault(status, 0)
        per_day[day][status] += 1
        totals[status] = totals.get(status, 0) + 1

    assert Attendance.objects.count() == 662, '考勤总数应为 662'
    assert totals.get('normal', 0) == 470, f'正常应为 470，实际 {totals.get("normal", 0)}'
    assert totals.get('late', 0) == 131, f'迟到应为 131，实际 {totals.get("late", 0)}'
    assert totals.get('early', 0) == 48, f'早退应为 48，实际 {totals.get("early", 0)}'
    assert totals.get('makeup', 0) == 13, f'补卡应为 13，实际 {totals.get("makeup", 0)}'
    print('[verify] 图4-7 合计：正常 470 / 迟到 131 / 早退 48 / 补卡 13 = 662 ✓')

    for idx, day in enumerate(days):
        got = per_day.get(day, {})
        want = {
            'normal': NORMAL[idx], 'late': LATE[idx],
            'early': EARLY[idx], 'makeup': MAKEUP[idx],
        }
        for status, count in want.items():
            if got.get(status, 0) != count:
                ok = False
                print(f'  ✗ {day} {status} 期望 {count} 实得 {got.get(status, 0)}')
    if ok:
        print('[verify] 图4-7 逐日 22 个工作日分布逐项吻合 ✓')

    # 图4-9：来源分布 + 总链
    dist = {}
    for plugin, action in BlockchainRecord.objects.values_list('plugin', 'action'):
        dist[plugin] = dist.get(plugin, 0) + 1
    assert BlockchainRecord.objects.count() == 693, '留痕总数应为 693'
    for plugin, count in FIG49_COUNTS.items():
        assert dist.get(plugin, 0) == count, (
            f'{plugin} 留痕应为 {count}，实际 {dist.get(plugin, 0)}')
    print(f'[verify] 图4-9 来源分布：{dist} 共 693 ✓')

    chain_ok, broken = BlockchainRecord.verify_chain()
    assert chain_ok, f'哈希链校验失败，断裂于 #{broken}'
    print('[verify] 哈希链 693 条逐条重算通过 ✓')

    assert Approval.objects.count() == 48, '审批单应为 48 张'
    assert ApprovalRecord.objects.count() == 64, (
        f'审批流转记录应为 64 条，实际 {ApprovalRecord.objects.count()}')
    assert Announcement.objects.count() == 6, '公告应为 6 条'
    assert AnnouncementRead.objects.count() == 94, '公告已读应为 94 条'

    print(f'[verify] 审批 48/{ApprovalRecord.objects.count()}，'
          f'公告 {Announcement.objects.count()}/{AnnouncementRead.objects.count()}，'
          f'站内信 {Notification.objects.count()}，'
          f'用户 {User.objects.count()}，部门 {Department.objects.count()}，'
          f'角色 {Role.objects.count()}')


def main():
    admin = User.objects.filter(is_superuser=True).order_by('id').first()
    assert admin, '缺少超级管理员，请先创建 admin'
    reset()
    ensure_org(admin)
    ensure_rule(admin)
    seed_structure(admin)
    seed_approvals(admin)
    seed_notices(admin)
    seed_attendance()
    verify()
    print('演示数据写入完成。')


if __name__ == '__main__':
    main()
