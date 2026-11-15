"""A 阶段只读工具集。

硬约束：
- 所有工具 `write=False`；A 阶段不存在 update / create / delete 工具；
- schema 的 enum 全部来自真实模型 choices，不抄文档里的旧示例；
- 权限码只放在 Python 元数据里，不放进 schema，避免向模型泄露越权提示。
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .models import Message  # noqa: F401  （确保 app 已加载，不参与逻辑）

MONTH_RE = re.compile(r'^\d{4}-\d{2}$')

# 助手能引导用户打开的站内页面白名单；不接收任意 URL，避免把模型输出当跳转目标。
PAGES = {
    'attendance': {
        'plugin': 'attendance',
        'permission': 'attendance_view',
        'url_name': 'attendance:attendance_dashboard',
        'title': '考勤打卡',
        'description': '打开考勤看板，在页面上完成签到或签退。',
    },
    'approval': {
        'plugin': 'approval',
        'permission': 'approval_view',
        'url_name': 'approval:approval_list',
        'title': '审批中心',
        'description': '打开发起、待办和已办审批的统一入口。',
    },
    'notice': {
        'plugin': 'notice',
        'permission': 'notice_view',
        'url_name': 'notice:notice_list',
        'title': '公告中心',
        'description': '打开公告列表，查看已读和未读通知。',
    },
    'approval_pending': {
        'plugin': 'approval',
        'permission': 'approval_approve',
        'url_name': 'approval:approval_pending',
        'title': '待我审批',
        'description': '打开待我审批列表，查看并处理分配给你的审批单。',
    },
    'approval_new': {
        'plugin': 'approval',
        'permission': 'approval_view',
        'url_name': 'approval:approval_create',
        'title': '发起审批',
        'description': '打开新建审批表单，由你本人填写并提交。',
    },
    'notice_new': {
        'plugin': 'notice',
        'permission': 'notice_manage',
        'url_name': 'notice:notice_create',
        'title': '发布公告',
        'description': '打开公告发布表单，由你本人填写并发布。',
    },
}


def _month_start(value):
    if not MONTH_RE.match(str(value or '')):
        raise ValueError('month 必须是 YYYY-MM 格式')
    year, month = (int(part) for part in value.split('-'))
    return date(year, month, 1)


def _month_qs(qs, month):
    start = _month_start(month)
    return qs.filter(created_at__year=start.year, created_at__month=start.month)


def _fmt_dt(value):
    if value is None:
        return ''
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M')


def _approval_type_values():
    from plugins.approval.models import Approval
    return [value for value, _label in Approval.Type.choices]


def _approval_status_values():
    from plugins.approval.models import Approval
    return [value for value, _label in Approval.Status.choices]


def search_approval(user, approval_type=None, status=None, month=None,
                    keyword=None, scope='applicant', limit=10):
    """按条件查审批单；只返回当前用户相关范围。"""
    from plugins.approval.models import Approval

    qs = Approval.objects.select_related('applicant', 'approver')
    if scope == 'applicant':
        # 对齐「我的申请」列表：申请人主动隐藏（或已被替换）的驳回单不再回显。
        qs = qs.filter(applicant=user, applicant_hidden=False)
    elif scope == 'approver':
        qs = qs.filter(approver=user)
    elif scope == 'cc':
        qs = qs.filter(cc_users=user).distinct()
    else:
        raise ValueError('scope 只能是 applicant / approver / cc')

    if approval_type:
        qs = qs.filter(approval_type=approval_type)
    if status:
        qs = qs.filter(status=status)
    if month:
        qs = _month_qs(qs, month)
    if keyword:
        qs = qs.filter(title__icontains=keyword)
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 10

    return {
        'total': qs.count(),
        'items': [{
            'id': item.pk,
            'type': item.approval_type,
            'type_label': item.get_approval_type_display(),
            'title': item.title,
            'status': item.status,
            'status_label': item.get_status_display(),
            'amount': str(item.amount) if item.amount is not None else '',
            'applicant': item.applicant.last_name or item.applicant.username,
            'approver': (item.approver.last_name or item.approver.username)
            if item.approver else '',
            'created_at': _fmt_dt(item.created_at),
        } for item in qs.order_by('-created_at')[:limit]],
    }


def _action_unavailable(reason, detail_url=''):
    return {
        'available': False,
        'reason': reason,
        'detail_url': detail_url,
    }


def open_page(user, page):
    """返回一个站内页面入口；只读，不打开浏览器、不代用户操作。"""
    meta = PAGES.get(page)
    if meta is None:
        return {'available': False, 'reason': 'unknown_page'}
    from plugin_host.registry import plugin_enabled
    if not plugin_enabled(meta['plugin']):
        return {'available': False, 'reason': 'plugin_disabled'}
    if not user.has_perm(meta['permission']):
        return {'available': False, 'reason': 'not_permitted'}
    return {
        'available': True,
        'page': page,
        'title': meta['title'],
        'description': meta['description'],
        'url': reverse(meta['url_name']),
        'requires_user_action': True,
    }


def prepare_approval_action(user, approval_id):
    """为当前用户准备一张只读审批动作卡；不写库、不流转。

    只覆盖普通单（请假/报销/用章/外出/加班/调休）。会签单
    （dept_delete / user_disable）会触发删除/禁用回调，C1 不提供卡片，
    由模型引导用户回到审批详情页处理。
    """
    from plugins.approval import services as approval_services
    from plugins.approval.models import Approval

    try:
        pk = int(approval_id)
    except (TypeError, ValueError):
        return _action_unavailable('not_found_or_forbidden')
    try:
        approval = Approval.objects.select_related(
            'applicant', 'approver').get(pk=pk)
    except Approval.DoesNotExist:
        return _action_unavailable('not_found_or_forbidden')

    detail_url = reverse(
        'approval:approval_detail', args=[approval.pk])
    if not approval_services.may_view(user, approval):
        # 不区分「不存在」与「无权查看」，避免 id 枚举泄露单据存在性。
        return _action_unavailable('not_found_or_forbidden')
    if approval.is_counter_signature():
        return _action_unavailable('counter_signature', detail_url)
    if not approval_services.can_act(user, approval):
        reason = ('not_pending' if approval.status != Approval.Status.PENDING
                  else 'not_approver')
        return _action_unavailable(reason, detail_url)

    return {
        'available': True,
        'action_card': {
            'approval_id': approval.pk,
            'type_label': approval.get_approval_type_display(),
            'title': approval.title,
            'applicant': (approval.applicant.last_name
                          or approval.applicant.username),
            'status_label': approval.get_status_display(),
            'amount': str(approval.amount) if approval.amount is not None else '',
            'created_at': _fmt_dt(approval.created_at),
            'detail_url': detail_url,
            'actions': [
                {'value': 'approve', 'label': '通过',
                 'confirm': '确认通过该申请？确认后不可修改。'},
                {'value': 'reject', 'label': '驳回',
                 'confirm': '确认驳回该申请？确认后不可修改。'},
            ],
        },
    }


def stats_approval_count(user, month, scope='approver'):
    """按状态统计审批单数量；scope=approver 即「我批了几单」。"""
    from plugins.approval.models import Approval

    qs = Approval.objects.all()
    if scope == 'applicant':
        qs = qs.filter(applicant=user, applicant_hidden=False)
    elif scope == 'approver':
        qs = qs.filter(approver=user)
    else:
        raise ValueError('scope 只能是 applicant / approver')
    if month:
        qs = _month_qs(qs, month)

    counts = {row['status']: row['count'] for row in
              qs.values('status').annotate(count=Count('id'))}
    result = {value: counts.get(value, 0) for value in _approval_status_values()}
    result['total'] = sum(result.values())
    return result


def stats_attendance(user, month):
    """统计当前用户一个月的考勤状态；不查他人。"""
    from plugins.attendance.models import Attendance

    qs = Attendance.objects.filter(user=user)
    if month:
        start = _month_start(month)
        qs = qs.filter(date__year=start.year, date__month=start.month)
    counts = {row['status']: row['count'] for row in
              qs.values('status').annotate(count=Count('id'))}
    result = {value: counts.get(value, 0) for value in
              [choice for choice, _label in Attendance.Status.choices]}
    result['days'] = qs.count()
    return result


def _draft_datetime(value):
    """把模型给的 datetime-local 值统一成 YYYY-MM-DDTHH:MM。"""
    text = str(value or '').strip()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%dT%H:%M')
        except ValueError:
            continue
    raise ValueError('时间格式应为 YYYY-MM-DDTHH:MM')


def _draft_date(value):
    """把模型给的日期统一成 YYYY-MM-DD。"""
    return date.fromisoformat(str(value or '').strip()).isoformat()


DRAFT_TYPES = {
    'leave': '请假',
    'expense': '报销',
    'seal': '用章',
    'outing': '外出',
    'overtime': '加班',
    'comp': '调休',
}


def _draft_result(approval_type, initial, fields):
    return {
        'draft': {
            'approval_type': approval_type,
            'type_label': DRAFT_TYPES[approval_type],
            'initial': initial,
            'fields': fields,
        },
    }


def _draft_span(start_time, end_time):
    """校验并规范化开始/结束时间，结束必须晚于开始。"""
    missing = []
    if not start_time:
        missing.append('开始时间')
    if not end_time:
        missing.append('结束时间')
    if missing:
        return None, {'missing': missing}
    try:
        start_value = _draft_datetime(start_time)
        end_value = _draft_datetime(end_time)
    except ValueError:
        return None, {'error': '时间格式应为 YYYY-MM-DDTHH:MM'}
    if end_value <= start_value:
        return None, {'error': '结束时间必须晚于开始时间'}
    return (start_value, end_value), None


def draft_approval(user, approval_type, leave_time=None, submit_time=None,
                   amount=None, reason=None, start_time=None, end_time=None,
                   seal_time=None):
    """生成六类审批草稿。只返回待确认数据，不写库、不提交。"""
    label = DRAFT_TYPES.get(approval_type)
    if label is None:
        return {
            'draft': None,
            'missing': [],
            'error': '目前只支持 leave/expense/seal/outing/overtime/comp',
        }
    reason = str(reason or '').strip()
    if len(reason) > 500:
        return {'draft': None, 'missing': [], 'error': '事由不能超过 500 字'}

    if approval_type == 'leave':
        if not leave_time:
            return {'draft': None, 'missing': ['请假时间']}
        try:
            leave_value = _draft_datetime(leave_time)
        except ValueError:
            return {
                'draft': None, 'missing': [],
                'error': '请假时间格式应为 YYYY-MM-DDTHH:MM',
            }
        initial = {'leave_time': leave_value}
        if reason:
            initial['reason'] = reason
        return _draft_result('leave', initial, [
            {'name': 'leave_time', 'label': '请假时间',
             'value': leave_value.replace('T', ' ')},
            {'name': 'reason', 'label': '事由', 'value': reason or '未填写'},
        ])

    if approval_type == 'expense':
        missing = []
        if not submit_time:
            missing.append('提交时间')
        if amount in (None, ''):
            missing.append('金额')
        if missing:
            return {'draft': None, 'missing': missing}
        try:
            submit_value = _draft_date(submit_time)
        except ValueError:
            return {
                'draft': None, 'missing': [],
                'error': '提交时间格式应为 YYYY-MM-DD',
            }
        try:
            amount_value = Decimal(str(amount)).quantize(Decimal('0.01'))
            if not amount_value.is_finite() or amount_value < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            return {'draft': None, 'missing': [], 'error': '金额必须是非负数字'}
        initial = {
            'submit_time': submit_value,
            'amount': f'{amount_value:.2f}',
        }
        if reason:
            initial['reason'] = reason
        return _draft_result('expense', initial, [
            {'name': 'submit_time', 'label': '提交时间', 'value': submit_value},
            {'name': 'amount', 'label': '金额', 'value': f'{amount_value:.2f}'},
            {'name': 'reason', 'label': '费用事由', 'value': reason or '未填写'},
        ])

    if approval_type == 'seal':
        if not seal_time:
            return {'draft': None, 'missing': ['用章时间']}
        try:
            seal_value = _draft_datetime(seal_time)
        except ValueError:
            return {
                'draft': None, 'missing': [],
                'error': '用章时间格式应为 YYYY-MM-DDTHH:MM',
            }
        initial = {'seal_time': seal_value}
        if reason:
            initial['purpose'] = reason
        return _draft_result('seal', initial, [
            {'name': 'seal_time', 'label': '用章时间',
             'value': seal_value.replace('T', ' ')},
            {'name': 'purpose', 'label': '用途', 'value': reason or '未填写'},
            {'name': 'seal_file', 'label': '用章文件', 'value': '请在卡片中选择'},
        ])

    span, error = _draft_span(start_time, end_time)
    if error:
        if 'missing' in error:
            return {'draft': None, 'missing': error['missing']}
        return {'draft': None, 'missing': [], 'error': error['error']}
    start_value, end_value = span
    initial = {'start_time': start_value, 'end_time': end_value}
    if reason and approval_type != 'comp':
        initial['reason'] = reason

    if approval_type == 'outing':
        labels = ('外出开始时间', '外出结束时间', '外出事由')
    elif approval_type == 'overtime':
        labels = ('加班开始时间', '加班结束时间', '加班事由')
    else:
        labels = ('调休开始时间', '调休结束时间', None)
    fields = [
        {'name': 'start_time', 'label': labels[0],
         'value': start_value.replace('T', ' ')},
        {'name': 'end_time', 'label': labels[1],
         'value': end_value.replace('T', ' ')},
    ]
    if labels[2]:
        fields.append({'name': 'reason', 'label': labels[2],
                       'value': reason or '未填写'})
    return _draft_result(approval_type, initial, fields)


def list_notice(user, limit=5, unread_only=False):
    """列出公告（全员可见），带当前用户是否已读。"""
    from plugins.notice.models import Announcement

    qs = Announcement.objects.select_related('publisher').all()
    if unread_only:
        qs = qs.exclude(read_records__user=user)
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 5
    return {
        'total': qs.count(),
        'items': [{
            'id': item.pk,
            'title': item.title,
            'publisher': item.publisher.last_name or item.publisher.username,
            'created_at': _fmt_dt(item.created_at),
            'is_read': item.read_records.filter(user=user).exists(),
            'is_top': item.is_top,
        } for item in qs.order_by('-is_top', '-created_at')[:limit]],
    }


def query_department(user, keyword=None, limit=10):
    """查部门（含成员数）；仅组织管理权限可用。"""
    from plugins.user.models import Department

    qs = Department.objects.filter(is_active=True)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 10
    return {
        'total': qs.count(),
        'items': [{
            'id': item.pk,
            'name': item.name,
            'parent': item.parent.name if item.parent else '',
            'member_count': item.members.filter(is_active=True).count(),
        } for item in qs.order_by('name')[:limit]],
    }


def search_user(user, keyword, limit=5):
    """按姓名/账号查用户；仅组织管理权限可用。"""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    qs = User.objects.filter(is_active=True).select_related('department')
    if keyword:
        qs = qs.filter(
            models_q(keyword)
        )
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 5
    return {
        'total': qs.count(),
        'items': [{
            'id': item.pk,
            'name': item.last_name or item.username,
            'username': item.username,
            'department': item.department.name if item.department else '',
            'roles': [role.name for role in item.roles.all()[:3]],
        } for item in qs.order_by('last_name', 'username')[:limit]],
    }


def models_q(keyword):
    """跨 last_name / username 的关键词 Q（延迟导入，避免工具模块顶部依赖）。"""
    from django.db.models import Q
    return Q(last_name__icontains=keyword) | Q(username__icontains=keyword)


# ---------------------------------------------------------------------------
# OpenAI 工具 schema
# ---------------------------------------------------------------------------

def _schema(name, description, properties, required=None):
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required or [],
            },
        },
    }


_SCOPE_APPROVAL = {
    'type': 'string',
    'enum': ['applicant', 'approver', 'cc'],
    'description': '查询范围：applicant=我发起的，approver=我审批的，cc=抄送我的',
}

_TOOL_SPECS = {}


def _register(name, fn, schema, permissions, description):
    _TOOL_SPECS[name] = {
        'fn': fn,
        'schema': schema,
        'required_permissions': permissions,
        'write': False,
        'max_calls_per_turn': 1,
    }


_register(
    'search_approval', search_approval,
    _schema('search_approval',
            '按条件查询审批单。只读。用户问「有哪些单子」「某个单的状态」时使用；'
            '不要用它统计数量，统计请用 stats_approval_count。',
            {
                'approval_type': {
                    'type': 'string', 'enum': _approval_type_values(),
                    'description': '审批类型，取值见枚举；不确定就不要填',
                },
                'status': {
                    'type': 'string', 'enum': _approval_status_values(),
                    'description': '审批状态',
                },
                'month': {'type': 'string', 'description': '月份，严格格式 YYYY-MM，例如 2026-11'},
                'keyword': {'type': 'string', 'description': '标题关键词'},
                'scope': _SCOPE_APPROVAL,
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20,
                          'description': '最多返回条数，默认 10'},
            }),
    ['approval_view'], '查询审批单'),
_register(
    'prepare_approval_action', prepare_approval_action,
    _schema('prepare_approval_action',
            '为一条待审批的普通单准备只读动作卡。只返回卡片元数据，不写库、'
            '不通过、不驳回；用户明确要求「通过 / 驳回某条审批」时使用。'
            '会签单（部门删除 / 用户禁用）不要调用本工具，直接让用户去审批详情处理。'
            '先确认用户说的是哪一条单；有多条候选就先问，不要猜。',
            {
                'approval_id': {
                    'type': 'integer', 'minimum': 1,
                    'description': '审批单 ID，来自 search_approval 返回的 id',
                },
            }, required=['approval_id']),
    ['approval_view'], '准备审批动作卡'),
_register(
    'draft_approval', draft_approval,
    _schema('draft_approval',
            '生成请假、报销、用章、外出、加班或调休草稿。只返回待确认字段，'
            '不写库、不提交。用户明确说「帮我请假 / 报销 / 用章 / 外出 / 加班 / '
            '调休 / 起草」时使用；缺时间、金额或起止时间就返回 missing 追问，'
            '不要替用户编造。部门与审批人交给审批表单默认值，不要填。',
            {
                'approval_type': {
                    'type': 'string', 'enum': list(DRAFT_TYPES),
                    'description': 'leave=请假，expense=报销，seal=用章，'
                                   'outing=外出，overtime=加班，comp=调休',
                },
                'leave_time': {
                    'type': 'string',
                    'description': '请假时间，格式 YYYY-MM-DDTHH:MM，例如 2026-11-15T09:00',
                },
                'submit_time': {
                    'type': 'string',
                    'description': '报销提交日期，格式 YYYY-MM-DD',
                },
                'amount': {
                    'type': 'number', 'minimum': 0,
                    'description': '报销金额，只填数字，不带货币符号',
                },
                'start_time': {
                    'type': 'string',
                    'description': '外出/加班/调休开始时间，格式 YYYY-MM-DDTHH:MM',
                },
                'end_time': {
                    'type': 'string',
                    'description': '外出/加班/调休结束时间，格式 YYYY-MM-DDTHH:MM',
                },
                'seal_time': {
                    'type': 'string',
                    'description': '用章时间，格式 YYYY-MM-DDTHH:MM',
                },
                'reason': {
                    'type': 'string',
                    'description': '事由或用途：请假事由、费用事由、外出事由、'
                                   '加班事由、用章用途，按用户原话概括，不要扩写',
                },
            }),
    ['approval_view'], '生成审批草稿'),
_register(
    'stats_approval_count', stats_approval_count,
    _schema('stats_approval_count',
            '按状态统计审批单数量。只读。用户问「这个月我批了几个单」时使用。',
            {
                'month': {'type': 'string', 'description': '月份，严格格式 YYYY-MM，例如 2026-11'},
                'scope': {
                    'type': 'string', 'enum': ['applicant', 'approver'],
                    'description': 'applicant=我发起的，approver=我审批的',
                },
            }, ['month']),
    ['approval_view'], '统计审批单数量'),
_register(
    'stats_attendance', stats_attendance,
    _schema('stats_attendance',
            '统计当前用户一个月的考勤状态。只读。用户问「我这个月迟到几次」时使用；'
            '不能查其他员工。',
            {
                'month': {'type': 'string', 'description': '月份，严格格式 YYYY-MM，例如 2026-11'},
            }, ['month']),
    ['attendance_view'], '统计本人考勤'),
_register(
    'open_page', open_page,
    _schema('open_page',
            '返回一个站内页面入口。只读：不打开浏览器、不代替用户点击、不写库。'
            '用户要求打开签到、审批、待办、新建审批、公告或发布公告页面，'
            '或某项操作必须到页面完成时使用；'
            '只能打开白名单里的页面，不要编造 URL。返回后只说明入口已准备好，'
            '不得声称已打开或已跳转。',
            {
                'page': {
                    'type': 'string',
                    'enum': list(PAGES),
                    'description': 'attendance=考勤打卡，approval=审批中心，notice=公告中心，'
                                   'approval_pending=待我审批，approval_new=发起审批，'
                                   'notice_new=发布公告',
                },
            }, ['page']),
    [], '打开站内页面')
_register(
    'list_notice', list_notice,
    _schema('list_notice',
            '列出公告。只读。用户问「最近有什么通知」时使用。',
            {
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20,
                          'description': '最多返回条数，默认 5'},
                'unread_only': {'type': 'boolean', 'description': '只看未读'},
            }),
    ['notice_view'], '列出公告'),
_register(
    'query_department', query_department,
    _schema('query_department',
            '查询部门及成员数。只读。仅组织管理权限可用。',
            {
                'keyword': {'type': 'string', 'description': '部门名称关键词'},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20,
                          'description': '最多返回条数，默认 10'},
            }),
    ['user_manage'], '查询部门'),
_register(
    'search_user', search_user,
    _schema('search_user',
            '按姓名或账号搜索用户。只读。仅组织管理权限可用。',
            {
                'keyword': {'type': 'string', 'description': '姓名或账号关键词'},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20,
                          'description': '最多返回条数，默认 5'},
            }, ['keyword']),
    ['user_manage'], '搜索用户'),

# 只读模式会收起这两类“需要用户确认后才落库”的工具：
# 它们本身不写库，但会生成可提交的草稿/动作卡，属于可写模式的产物。
READ_WRITE_TOOLS = frozenset({'draft_approval', 'prepare_approval_action'})

# 兼容 docs/ai-tool-calling.md 里的 TOOLS 名称
TOOLS = _TOOL_SPECS
assert all(not spec['write'] for spec in TOOLS.values()), 'A 阶段不允许存在写工具'


def schemas():
    return [spec['schema'] for spec in TOOLS.values()]


def allowed_names_for(user, read_only=False):
    """按权限过滤工具名；权限判定集中在 registry。

    只读模式在权限结果之上再移除草稿和动作卡工具；这是模式语义，
    不是权限降级，所以放在权限过滤之后。
    """
    from plugin_host.registry import _user_perm_codenames

    allowed = _user_perm_codenames(user)
    if allowed is None:
        names = set(TOOLS)
    else:
        names = {
            name for name, spec in TOOLS.items()
            if all(perm in allowed for perm in spec['required_permissions'])
        }
    if read_only:
        names -= READ_WRITE_TOOLS
    return names
