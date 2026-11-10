"""当前请求用户（contextvar），供审计字段自动填充（v1.7.8）。

照 `plugin_host/theming.py` 的 token 写法：中间件入口 set、`finally` reset。

**重要边界（与 `request_id.py` 同一条，v1.7.5 实测过）**：
`RequestIdMiddleware` / `CurrentUserMiddleware` 在 `finally` 里复位 contextvar，而
`django.request` 的 4xx/5xx 日志、`process_response` 之后的代码都在复位**之后**执行。
所以：

> 任何在 `process_response` / `response_for_exception` 之后、或响应阶段信号里读取本模块
> contextvar 的代码，拿到的都是空值，而且**不会报错**。

审计填充发生在 `pre_save`（写库期间），在复位之前，所以安全；将来若做「响应阶段记录审计」，
请改用 `request.request_id` 那种挂在请求对象上的方式。
"""

import contextvars

_CURRENT_USER = contextvars.ContextVar('current_user', default=None)


def set_current_user(user):
    """在当前上下文写入用户（未登录请传 None，不要传 AnonymousUser）。"""
    return _CURRENT_USER.set(user)


def reset_current_user(token):
    _CURRENT_USER.reset(token)


def get_current_user():
    """当前请求用户；无上下文（shell / 后台线程 / 响应阶段）返回 None。"""
    return _CURRENT_USER.get()
