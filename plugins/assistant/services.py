"""对话服务：校验、执行循环、会话落库。

入口是 `chat_turn()`；视图只负责取参数、渲染和重定向。
"""

import json
import re

from django.utils import timezone

from . import llm
from .models import Conversation, Message
from .tools import TOOLS, allowed_names_for

MONTH_RE = re.compile(r'^\d{4}-\d{2}$')
DENIED = '__DENIED__'


def build_system_prompt(user):
    today = timezone.localdate().isoformat()
    name = getattr(user, 'last_name', '') or getattr(user, 'username', '')
    return (
        f'你是 Constellatio 的企业助手。当前用户：{name}；今天：{today}。\n'
        '规则：\n'
        '1. 只回答与当前办公系统有关的问题；不确定时明确说不知道，不要编造。\n'
        '2. 需要业务数据时调用提供的只读工具，不要凭记忆编造数字。\n'
        '3. 用户问审批、考勤、公告、部门、人员时，优先用工具查询。\n'
        '4. 工具返回错误就向用户解释，不要反复调用同一个工具。\n'
        '5. 一律使用简体中文回答，语气简洁。\n'
        '6. 不要使用 Markdown 标记（*、#、反引号）；用纯文本短句和换行。'
    )


def validate_tool_call(tc, user, allowed_names, turn_state):
    """返回 (ok, args_or_error)；权限不足返回 (False, '__DENIED__')。"""
    if not isinstance(tc, dict):
        return False, 'tool_call 结构不合法'
    function = tc.get('function') or {}
    name = function.get('name')
    if name not in TOOLS:
        return False, f'工具 {name!r} 不存在。可用工具：{sorted(allowed_names)}'

    raw = function.get('arguments', '')
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return False, 'arguments 必须是合法 JSON，例如 {"month":"2026-11"}'
    if not isinstance(args, dict):
        return False, 'arguments 必须是 JSON 对象'

    spec = TOOLS[name]['schema']['function']['parameters']['properties']
    extra = set(args) - set(spec)
    if extra:
        return False, f'这些参数不存在：{sorted(extra)}。只允许：{sorted(spec)}'
    required = TOOLS[name]['schema']['function']['parameters'].get('required') or []
    missing = [key for key in required if key not in args]
    if missing:
        return False, f'缺少必填参数：{missing}'

    for key, value in args.items():
        declared = spec[key]
        if 'enum' in declared and value not in declared['enum']:
            return False, f'参数 {key} 只能是 {declared["enum"]}，你给的是 {value!r}'
        expected = declared.get('type')
        if expected == 'integer' and (isinstance(value, bool) or not isinstance(value, int)):
            return False, f'参数 {key} 必须是整数'
        if expected == 'boolean' and not isinstance(value, bool):
            return False, f'参数 {key} 必须是布尔值'
        if expected == 'string' and not isinstance(value, str):
            return False, f'参数 {key} 必须是字符串'

    if 'month' in args and not MONTH_RE.match(str(args['month'])):
        return False, f'month 必须是 YYYY-MM 格式，你给的是 {args["month"]!r}'

    if turn_state['calls'].get(name, 0) >= TOOLS[name]['max_calls_per_turn']:
        return False, f'工具 {name} 本轮已调过，不要重复调用'

    if name not in allowed_names:
        return False, DENIED

    return True, args


def _normalise_tool_calls(tool_calls):
    """补齐缺失 id、截断到 3 条；模型侧参数仍保持原样交给校验层。"""
    result = []
    for index, tc in enumerate((tool_calls or [])[:3]):
        if not isinstance(tc, dict):
            continue
        item = dict(tc)
        if not item.get('id'):
            item['id'] = f'call_{index + 1}'
        function = item.get('function')
        if not isinstance(function, dict):
            function = {}
        item['function'] = {
            'name': function.get('name', ''),
            'arguments': function.get('arguments', ''),
        }
        result.append(item)
    return result


def run_turn(user, messages, config=None, max_rounds=3):
    """一次用户输入 → 最终回答。返回 (reply_text, logs)。"""
    allowed_names = allowed_names_for(user)
    tools = [TOOLS[name]['schema'] for name in TOOLS if name in allowed_names]
    logs = []
    turn_state = {'calls': {}}

    for _round in range(max_rounds):
        message = llm.call_llm(messages, tools=tools or None, config=config)
        tool_calls = _normalise_tool_calls(message.get('tool_calls'))
        if not tool_calls:
            content = (message.get('content') or '').strip()
            if content:
                return content, logs
            raise llm.BadResponse('没听清，能再说具体一点吗？')

        messages.append({
            'role': 'assistant',
            'content': message.get('content') or '',
            'tool_calls': tool_calls,
        })
        for tc in tool_calls:
            ok, args = validate_tool_call(tc, user, allowed_names, turn_state)
            if not ok and args == DENIED:
                return '你没有执行这个操作所需的权限。', logs
            if not ok:
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc['id'],
                    'content': json.dumps({'error': args}, ensure_ascii=False),
                })
                continue

            name = tc['function']['name']
            turn_state['calls'][name] = turn_state['calls'].get(name, 0) + 1
            try:
                result = TOOLS[name]['fn'](user, **args)
            except Exception as exc:  # 单次工具失败不拖垮整轮对话
                result = {'error': type(exc).__name__}
            logs.append({'tool': name, 'args': args})
            messages.append({
                'role': 'tool',
                'tool_call_id': tc['id'],
                'content': json.dumps(result, ensure_ascii=False, default=str),
            })

    return '这个问题我没法确定，能再说具体一点吗？', logs


def _history(conversation, limit=20):
    rows = list(conversation.messages.filter(
        role__in=[Message.Role.USER, Message.Role.ASSISTANT]
    ).order_by('-created_at', '-pk')[:limit])
    rows.reverse()
    return [{'role': row.role, 'content': row.content} for row in rows]


def chat_turn(user, conversation, text):
    """保存用户消息 → 模型/工具循环 → 保存助手回复。返回助手文本。"""
    history = _history(conversation)
    Message.objects.create(
        conversation=conversation, role=Message.Role.USER, content=text)
    if not conversation.title:
        conversation.title = text[:24]
        conversation.save(update_fields=['title', 'updated_at'])
    else:
        conversation.save(update_fields=['updated_at'])

    messages = [{'role': 'system', 'content': build_system_prompt(user)}]
    messages.extend(history)
    messages.append({'role': 'user', 'content': text})

    try:
        reply, _logs = run_turn(user, messages)
    except llm.AssistantError as exc:
        reply = str(exc)

    Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, content=reply)
    conversation.save(update_fields=['updated_at'])
    return reply


def get_conversation(user, pk):
    """按 id 取当前用户的会话；不存在或不属于本人返回 None（视图统一 404）。"""
    if not pk:
        return None
    try:
        return Conversation.objects.get(pk=pk, user=user)
    except (Conversation.DoesNotExist, ValueError, TypeError):
        return None
