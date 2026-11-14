"""固定问句评分：只看首轮工具名与参数，不评价最终措辞。

评分口径（与 `docs/ai-assistant-plan.md` 的 20 条 / 70% 验收一致）：
- 首轮必须恰好调用一个工具；
- 工具名必须与用例期望一致；
- 参数必须覆盖用户明确说出的槽位（月份 / 范围 / 类型 / 状态 / 关键词 / 条数 / 未读）；
- 工具默认值可以省略（如 `search_approval` 默认 applicant、`stats_approval_count` 默认 approver）；
- 用户没要求条数时，模型显式给 `limit` 不算错；其余未要求的过滤条件算错。
"""

import json
import re

from . import services
from .tools import TOOLS

TOOL_DEFAULTS = {
    'search_approval': {'scope': 'applicant', 'limit': 10},
    'stats_approval_count': {'scope': 'approver'},
    'stats_attendance': {},
    'list_notice': {'limit': 5, 'unread_only': False},
    'query_department': {'limit': 10},
    'search_user': {'limit': 5},
}


def _effective_args(tool_name, args):
    effective = dict(TOOL_DEFAULTS.get(tool_name, {}))
    effective.update(args)
    return {
        key: value for key, value in effective.items()
        if value is not None and value != ''
    }


def _decode_arguments(tool_call):
    function = tool_call.get('function') if isinstance(tool_call, dict) else None
    if not isinstance(function, dict):
        return None, 'tool_call 缺少 function'
    raw = function.get('arguments', '')
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None, 'arguments 不是合法 JSON'
    if not isinstance(args, dict):
        return None, 'arguments 不是 JSON 对象'
    return args, ''


def evaluate_message(case, message):
    """返回单条用例的判定；不执行数据库查询。"""
    tool_calls = message.get('tool_calls') if isinstance(message, dict) else None
    if not tool_calls:
        return {'id': case['id'], 'passed': False, 'tool': None, 'args': None,
                'reason': '首轮未调用工具'}
    if len(tool_calls) != 1:
        return {'id': case['id'], 'passed': False, 'tool': None, 'args': None,
                'reason': f'首轮调用了 {len(tool_calls)} 个工具，预期 1 个'}

    tool_call = tool_calls[0]
    function = tool_call.get('function') if isinstance(tool_call, dict) else {}
    tool_name = function.get('name') if isinstance(function, dict) else None
    args, error = _decode_arguments(tool_call)
    if error:
        return {'id': case['id'], 'passed': False, 'tool': tool_name,
                'args': None, 'reason': error}
    if tool_name != case['tool']:
        return {'id': case['id'], 'passed': False, 'tool': tool_name,
                'args': args, 'reason': f'工具应为 {case["tool"]}'}

    ok, checked = services.validate_tool_call(
        tool_call, None, set(TOOLS), {'calls': {}})
    if not ok:
        return {'id': case['id'], 'passed': False, 'tool': tool_name,
                'args': args, 'reason': checked}
    args = checked

    effective = _effective_args(tool_name, args)
    expect = case.get('expect') or {}
    contains = case.get('contains') or {}

    for key, wanted in expect.items():
        if key not in effective:
            return {'id': case['id'], 'passed': False, 'tool': tool_name,
                    'args': args, 'reason': f'缺少参数 {key}'}
        if effective[key] != wanted:
            return {'id': case['id'], 'passed': False, 'tool': tool_name,
                    'args': args,
                    'reason': f'参数 {key}={effective[key]!r}，应为 {wanted!r}'}

    for key, wanted in contains.items():
        if key not in effective:
            return {'id': case['id'], 'passed': False, 'tool': tool_name,
                    'args': args, 'reason': f'缺少参数 {key}'}
        if str(wanted).lower() not in str(effective[key]).lower():
            return {'id': case['id'], 'passed': False, 'tool': tool_name,
                    'args': args,
                    'reason': f'参数 {key}={effective[key]!r}，应包含 {wanted!r}'}

    for key, value in effective.items():
        if key in expect or key in contains:
            continue
        defaults = TOOL_DEFAULTS.get(tool_name, {})
        if key in defaults and value == defaults[key]:
            continue
        # 用户没要求条数时，模型显式给 limit 不改变"查什么"，不作为错误。
        if key == 'limit' and 'limit' not in expect:
            continue
        return {'id': case['id'], 'passed': False, 'tool': tool_name,
                'args': args, 'reason': f'多出未要求的参数 {key}={value!r}'}

    return {'id': case['id'], 'passed': True, 'tool': tool_name,
            'args': args, 'reason': ''}


def summarise(results, threshold=0.70):
    total = len(results)
    passed = sum(1 for result in results if result['passed'])
    rate = (passed / total) if total else 0.0
    return {
        'total': total,
        'passed': passed,
        'rate': rate,
        'threshold': threshold,
        'met': rate >= threshold,
    }


def model_tier(model):
    """按模型名粗分档位；只用于标注结果，不参与评分。"""
    tokens = re.sub(r'[^a-z0-9]+', ' ', (model or '').lower()).split()
    if '4b' in tokens:
        return '4b'
    return 'other'
