"""企业 SSO Ticket 签发 / 校验（HMAC-SHA256）。

Ticket 结构：`base64url(payload).base64url(hmac_sha256(secret, payload_b64))`
payload 为 JSON（username/sub/name/email/department/iat/exp）；网关只持有共享密钥即可签发。
"""

import base64
import hashlib
import hmac
import json
import time

from django.conf import settings
from django.core.cache import cache


class TicketError(Exception):
    """Ticket 非法 / 过期 / 重放。"""


def _secret():
    secret = getattr(settings, 'SSO_SHARED_SECRET', '')
    if not secret:
        raise TicketError('SSO 未配置共享密钥')
    return secret.encode('utf-8')


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _b64decode(text: str) -> bytes:
    padding = '=' * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def issue(payload: dict, ttl=None) -> str:
    """签发 Ticket：自动补 iat / exp（秒）。"""
    ttl = int(ttl if ttl is not None else getattr(settings, 'SSO_TICKET_TTL', 300))
    body = dict(payload)
    now = int(time.time())
    body.setdefault('iat', now)
    body['exp'] = now + ttl
    encoded = _b64encode(json.dumps(
        body, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8'))
    signature = hmac.new(_secret(), encoded.encode('ascii'), hashlib.sha256).digest()
    return f'{encoded}.{_b64encode(signature)}'


def verify(ticket: str, now=None) -> dict:
    """校验签名 / 期限 / 重放，返回 payload；任何异常统一 TicketError。"""
    if not ticket or ticket.count('.') != 1:
        raise TicketError('Ticket 格式错误')
    encoded, signature = ticket.split('.', 1)
    try:
        expected = hmac.new(_secret(), encoded.encode('ascii'), hashlib.sha256).digest()
        provided = _b64decode(signature)
    except (ValueError, UnicodeEncodeError) as exc:
        raise TicketError('Ticket 签名非法') from exc
    if not hmac.compare_digest(expected, provided):
        raise TicketError('Ticket 签名校验失败')

    try:
        payload = json.loads(_b64decode(encoded).decode('utf-8'))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TicketError('Ticket 内容非法') from exc
    if not isinstance(payload, dict):
        raise TicketError('Ticket 内容非法')

    expires = payload.get('exp')
    current = int(now if now is not None else time.time())
    if not isinstance(expires, int) or expires <= current:
        raise TicketError('Ticket 已过期')
    if payload.get('iat') and payload['iat'] > current + 60:
        raise TicketError('Ticket 时间非法')

    # 防重放：TTL 内同一 Ticket 只允许使用一次（进程内缓存；多 worker 需共享缓存）
    cache_key = 'sso:ticket:' + hashlib.sha256(ticket.encode('utf-8')).hexdigest()
    if not cache.add(cache_key, True, timeout=max(expires - current, 1)):
        raise TicketError('Ticket 已使用')
    return payload
