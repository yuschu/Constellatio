"""CSP（Content-Security-Policy）中间件（v1.7.16）。

设计要点：
- **每请求一个 nonce**：在 `__call__` 里生成一次并挂到 `request.csp_nonce`，模板里
  `{{ request.csp_nonce }}` 读取同一个值；禁止在模板/helper 里二次生成（否则同一响应里
  多个 script 的 nonce 会不一致，浏览器只放行其中一个）。
- **位置在 `SecurityMiddleware` 之后、所有项目中间件之前**：响应阶段自下而上，
  放最外层才能保证 `ExceptionGuardMiddleware` 渲染的 400/403 也带上 CSP 头。
- **硬 500 走 `handler500`**（本模块的 `server_error`）：Django 的默认 500 是在中间件链
  之外生成的，`__call__` 的响应阶段拿不到它，所以必须由 `handler500` 补头（nonce 复用
  `request.csp_nonce`，此时请求已进入过本中间件）。
- **静态文件不加**：`/static/` 下的响应由 whitenoise 返回，CSP 对图片/样式无意义且会污染日志。
- **不给 `script-src` 加 `'unsafe-inline'`**：那等于这条 CSP 在脚本面零防护；
  内联脚本靠 nonce、内联事件靠 `data-confirm` + `static/js/confirm.js` 改造（v1.7.16）。
- **`style-src` 保留 `'unsafe-inline'`**：全站 137+ 处 `style="…"` 属性（含图表容器高度），
  收紧会让排版与图表直接崩；防护重心是脚本执行面（业界通行取舍）。
"""

import secrets

from django.conf import settings
from django.views import defaults

NONCE_ATTR = 'csp_nonce'

# 指令顺序与文档 §1 保持一致，便于比对（CSP 对顺序无要求）
DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self' 'nonce-{nonce}'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
)


def new_nonce():
    """每个请求/每个响应一个 nonce（128 bit 随机，URL-safe 字符，可直接进 HTTP 头）。"""
    return secrets.token_urlsafe(16)


def build_policy(nonce):
    """拼成单行策略字符串；`nonce` 为空时保留占位以保持头结构可解析（不应发生）。"""
    return '; '.join(DIRECTIVES).format(nonce=nonce or '')


def _is_static(path):
    static_url = (getattr(settings, 'STATIC_URL', '') or '').lstrip('/')
    return bool(static_url) and path.lstrip('/').startswith(static_url)


class CspMiddleware:
    """给每个 HTML 响应下发 CSP，并保证同一响应内 script nonce 一致。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = new_nonce()
        request.csp_nonce = nonce          # 模板通过 {{ request.csp_nonce }} 读取
        response = self.get_response(request)
        if not _is_static(request.path_info):
            response['Content-Security-Policy'] = build_policy(nonce)
        return response


def server_error(request):
    """handler500：默认 500 在中间件链之外生成，这里补上 CSP 头（nonce 复用请求上的值）。"""
    response = defaults.server_error(request)
    nonce = getattr(request, NONCE_ATTR, None) or new_nonce()
    response['Content-Security-Policy'] = build_policy(nonce)
    return response
