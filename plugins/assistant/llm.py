"""OpenAI 兼容的最小客户端（A 阶段）。

约束（`docs/ai-tool-calling.md`）：
- 只用标准库 `urllib.request`，不引入 requests / httpx / openai SDK；
- 这是助手插件唯一的出网点；
- 任何异常都不把内部地址、API Key 或 traceback 抛给前端。
"""

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from .crypto import decrypt_secret


class AssistantError(Exception):
    """助手可预期的失败；message 直接作为用户可见提示。"""

    code = 'assistant_error'


class NotConfigured(AssistantError):
    code = 'not_configured'


class Unavailable(AssistantError):
    code = 'unavailable'


class AuthError(AssistantError):
    code = 'auth_error'


class BadResponse(AssistantError):
    code = 'bad_response'


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ''
    timeout: float = 30.0
    max_tokens: int = 1024

    @property
    def endpoint(self):
        return f'{self.base_url.rstrip("/")}/chat/completions'


def _stored_settings():
    """读取单例配置；迁移尚未应用/表不可用时回退环境变量。"""
    try:
        from .models import LLMSettings
        return LLMSettings.load()
    except (OperationalError, ProgrammingError):
        return None


def raw_config():
    """当前生效的五项配置（含 API Key），数据库优先、环境变量兜底。"""
    row = _stored_settings()
    return {
        'base_url': ((row.base_url if row else '') or
                     getattr(settings, 'ASSISTANT_LLM_BASE_URL', '') or '').strip(),
        'model': ((row.model if row else '') or
                  getattr(settings, 'ASSISTANT_LLM_MODEL', '') or '').strip(),
        'api_key': (decrypt_secret(row.api_key if row else '') or
                    getattr(settings, 'ASSISTANT_LLM_API_KEY', '') or '').strip(),
        'timeout': float((row.timeout_seconds if row else 0) or
                         getattr(settings, 'ASSISTANT_LLM_TIMEOUT', 30) or 30),
        'max_tokens': int((row.max_tokens if row else 0) or
                          getattr(settings, 'ASSISTANT_LLM_MAX_TOKENS', 1024) or 1024),
    }


def get_config():
    """组装为 LLMConfig；base_url / model 缺一即 NotConfigured。"""
    values = raw_config()
    if not values['base_url'] or not values['model']:
        raise NotConfigured('助手尚未配置模型服务')
    return LLMConfig(
        base_url=values['base_url'],
        model=values['model'],
        api_key=values['api_key'],
        timeout=values['timeout'],
        max_tokens=values['max_tokens'],
    )


def is_configured():
    try:
        get_config()
    except NotConfigured:
        return False
    return True


def call_llm(messages, tools=None, tool_choice='auto', config=None):
    """POST /chat/completions，返回首个 choice 的 message dict。

    `messages` 必须是 OpenAI Chat 格式；`tools` 为 None 时不发 tools。
    网络/协议异常统一转成 AssistantError 子类，调用方只负责展示提示。
    """
    cfg = config or get_config()
    payload = {
        'model': cfg.model,
        'messages': messages,
        'temperature': 0.2,
        'max_tokens': cfg.max_tokens,
    }
    if tools:
        payload['tools'] = tools
        payload['tool_choice'] = tool_choice

    headers = {'Content-Type': 'application/json'}
    if cfg.api_key:
        headers['Authorization'] = f'Bearer {cfg.api_key}'
    request = urllib.request.Request(
        cfg.endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers=headers,
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=cfg.timeout) as response:
            raw = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise AuthError('模型服务鉴权失败，请检查 API Key') from exc
        raise Unavailable('模型服务返回错误') from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        raise Unavailable('助手暂不可用，模型服务连接失败') from exc

    try:
        data = json.loads(raw)
        message = data['choices'][0]['message']
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise BadResponse('模型服务返回格式异常') from exc
    if not isinstance(message, dict):
        raise BadResponse('模型服务返回格式异常')
    return message


def probe(config=None):
    """连通性自检：是否连通、本次请求耗时、是否本机/内网、是否支持工具调用。

    发一条最短请求，带一个最小工具定义；不把服务返回的原文带到页面上。
    非流式请求无法切出首字时间，`latency_ms` 是整轮探测耗时，不含排队等待。
    """
    cfg = config or get_config()
    started = time.monotonic()
    message = call_llm(
        [{'role': 'user', 'content': '请调用一次 ping 工具，不要直接回答文字。'}],
        tools=[{
            'type': 'function',
            'function': {
                'name': 'ping',
                'description': '连通性探测，不需要业务数据。',
                'parameters': {'type': 'object', 'properties': {}},
            },
        }],
        config=cfg,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        'ok': True,
        'latency_ms': elapsed_ms,
        'is_local': is_local_base(cfg.base_url),
        'supports_tools': bool(message.get('tool_calls')),
        'model': cfg.model,
    }


def is_local_base(base_url):
    """base_url 是否指向本机/内网（用于配置页明确数据流向）。"""
    host = (urlparse(base_url).hostname or '').lower()
    if host in ('localhost', '127.0.0.1', '::1', 'ollama',
                'host.docker.internal', 'host.containers.internal'):
        return True
    if host.startswith('127.') or host == '0.0.0.0':
        return True
    try:
        import ipaddress
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback
    except ValueError:
        return host.endswith('.local')
