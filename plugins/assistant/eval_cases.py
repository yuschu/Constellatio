"""A 阶段固定问句验收集（20 条）。

每条只验证两件事：**选中了哪个工具**、**参数是否符合用户意图**。
不评价最终措辞，避免把"回答好不好听"混进工具调用验收。

月份分两类：
- 固定月份用绝对日期，保证同一套问句可以长期重跑；
- 相对月份（这个月 / 上个月）按运行当天推算，考的是模型对系统提示里
  "今天"的理解，不写死日期。
"""

from datetime import date


def _shift_month(day, delta):
    index = day.year * 12 + day.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1).strftime('%Y-%m')


def build_cases(today=None):
    """返回 20 条用例；`today` 仅供测试注入，生产按本地日期。"""
    today = today or date.today()
    this_month = today.strftime('%Y-%m')
    last_month = _shift_month(today, -1)

    return [
        {
            'id': 'A01',
            'question': '统计一下 2026-11 我审批了多少单。',
            'tool': 'stats_approval_count',
            'expect': {'month': '2026-11', 'scope': 'approver'},
        },
        {
            'id': 'A02',
            'question': '2026-10 我提交了多少张审批单？',
            'tool': 'stats_approval_count',
            'expect': {'month': '2026-10', 'scope': 'applicant'},
        },
        {
            'id': 'A03',
            'question': '这个月我一共批了几单？',
            'tool': 'stats_approval_count',
            'expect': {'month': this_month, 'scope': 'approver'},
        },
        {
            'id': 'A04',
            'question': '上个月我提交了几单？',
            'tool': 'stats_approval_count',
            'expect': {'month': last_month, 'scope': 'applicant'},
        },
        {
            'id': 'A05',
            'question': '帮我查 2026-11 我提交的请假单有哪些。',
            'tool': 'search_approval',
            'expect': {'month': '2026-11', 'scope': 'applicant',
                       'approval_type': 'leave'},
        },
        {
            'id': 'A06',
            'question': '我审批过的报销单有哪些？',
            'tool': 'search_approval',
            'expect': {'scope': 'approver', 'approval_type': 'expense'},
        },
        {
            'id': 'A07',
            'question': '有哪些审批单抄送给我了？',
            'tool': 'search_approval',
            'expect': {'scope': 'cc'},
        },
        {
            'id': 'A08',
            'question': '找一下标题里包含“采购”的审批单。',
            'tool': 'search_approval',
            'expect': {'scope': 'applicant'},
            'contains': {'keyword': '采购'},
        },
        {
            'id': 'A09',
            'question': '查一下 2026-10 已通过的用章申请。',
            'tool': 'search_approval',
            'expect': {'month': '2026-10', 'scope': 'applicant',
                       'status': 'approved', 'approval_type': 'seal'},
        },
        {
            'id': 'A10',
            'question': '我发起的审批里，还有哪些在待审批？',
            'tool': 'search_approval',
            'expect': {'scope': 'applicant', 'status': 'pending'},
        },
        {
            'id': 'A11',
            'question': '给我看最近 5 条待我审批的单子。',
            'tool': 'search_approval',
            'expect': {'scope': 'approver', 'status': 'pending', 'limit': 5},
        },
        {
            'id': 'A12',
            'question': '统计我 2026-11 的考勤情况。',
            'tool': 'stats_attendance',
            'expect': {'month': '2026-11'},
        },
        {
            'id': 'A13',
            'question': '上个月我的考勤怎么样？',
            'tool': 'stats_attendance',
            'expect': {'month': last_month},
        },
        {
            'id': 'A14',
            'question': '最近有什么公告？',
            'tool': 'list_notice',
            'expect': {},
        },
        {
            'id': 'A15',
            'question': '列出最近 10 条我还没读的公告。',
            'tool': 'list_notice',
            'expect': {'limit': 10, 'unread_only': True},
        },
        {
            'id': 'A16',
            'question': '有没有我还没读的通知？',
            'tool': 'list_notice',
            'expect': {'unread_only': True},
        },
        {
            'id': 'A17',
            'question': '技术部现在有多少人？',
            'tool': 'query_department',
            'expect': {},
            'contains': {'keyword': '技术'},
        },
        {
            'id': 'A18',
            'question': '公司有哪些部门？',
            'tool': 'query_department',
            'expect': {},
        },
        {
            'id': 'A19',
            'question': '帮我找一下叫张伟的同事。',
            'tool': 'search_user',
            'expect': {},
            'contains': {'keyword': '张伟'},
        },
        {
            'id': 'A20',
            'question': '账号 zhangsan 是谁？',
            'tool': 'search_user',
            'expect': {},
            'contains': {'keyword': 'zhangsan'},
        },
    ]
