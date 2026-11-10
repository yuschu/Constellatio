"""请求级 request_id：contextvar 保存，日志 filter 注入，中间件写响应头（v1.7.5）。

为什么用 contextvar 而不是把 request 传进 logger：
- gunicorn 是多线程/多 worker，模块级全局变量会串号；
- `%(request_id)s` 只能由 **filter** 注入，直写进 formatter 会让启动期 / `manage.py`
  这类没有 request_id 的日志抛 KeyError，而 logging 默认吞掉 handler 错误——表现为
  「日志静默丢失」。

**重要边界（v1.7.5 实测踩过，别再用错）**：
`RequestIdMiddleware` 在 `finally` 里 reset contextvar，而 `django.request` 的 4xx/5xx
日志是由 `BaseHandler.get_response()` 在**整个中间件栈返回之后**才发出的
（`django/core/handlers/base.py`：`response = self._middleware_chain(request)` 之后才
`log_response(...)`）。所以：

> 任何在 `process_response` / `response_for_exception` 之后、或响应阶段信号里读取本模块
> contextvar 的代码，拿到的都是空值（`current_request_id()` 返回 `-`），而且**不会报错**。

这条不只影响日志：将来若用 contextvar 做审计字段自动填充（`created_by` / `updated_by`），
在这些阶段读它就会静默填成 None。要在响应阶段取号，请读 `request.request_id`
（由 `RequestIdMiddleware` 挂在请求对象上），日志侧则由 `RequestIdFilter` 做同样的优先级回退。
"""

import contextvars

_REQUEST_ID = contextvars.ContextVar('request_id', default=None)


def set_request_id(value):
    """在当前上下文写入 request_id，返回用于恢复的 token。"""
    return _REQUEST_ID.set(value)


def reset_request_id(token):
    """恢复上一个上下文（中间件 finally 调用），避免线程复用时串号。"""
    _REQUEST_ID.reset(token)


def current_request_id():
    """当前 request_id；非请求上下文（shell / 启动期 / 管理命令）返回 '-'。"""
    return _REQUEST_ID.get() or '-'


class RequestIdFilter:
    """把 request_id 注入 LogRecord，供 `%(request_id)s` 使用。

    **优先级：request 属性 > contextvar**。
    `django.request` 的 4xx/5xx 日志由 `BaseHandler.get_response()` 在中间件栈**返回之后**
    才发出（`log_response` 在 `self._middleware_chain(request)` 之后调用），此时中间件
    已经 reset 了 contextvar——只读 contextvar 会记成 `-`，排障时对不上号。
    好在 `log_response` 把 request 塞进了 `extra`（来源：`django/utils/log.py`），
    所以从 `record.request.request_id` 取。
    """

    def filter(self, record):
        request = getattr(record, 'request', None)
        record.request_id = getattr(request, 'request_id', None) or current_request_id()
        return True
