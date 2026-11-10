"""容器中间件：主题选择 + 语言默认值 + 插件路由请求级守卫。

v1.5.7：语言中间件归属容器——language 插件停用后仍沿用最后设置的语言。
v1.5.8：主题运行时切换——按 Cookie 选择主题，模板由 ThemeLoader 按请求解析。
v1.7.4：登录守卫改由框架中间件承担，职责划分如下（三层不要混）：
  1. `django.contrib.auth.middleware.LoginRequiredMiddleware`（框架，settings.MIDDLEWARE
     第 9 位）只管「登没登录」：匿名请求在 `process_view` 阶段就被拦下，跳 `LOGIN_URL`
     并带回 `next`；唯一放行方式是视图上显式标注 `@login_not_required`。
  2. `plugin_host.permissions.require_perm`（插件视图装饰器）只管「有没有权限码」：
     在登录之后判定，缺权限码 302 回工作台。不在中间件里做权限判定。
  3. 本文件的三个中间件只管语言默认值 / 主题选择 / 插件启停路由（404），
     都不做身份或权限判定。
"""

import logging
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotFound, JsonResponse
from django.middleware.locale import LocaleMiddleware
from django.shortcuts import render
from django.utils import translation

from plugin_host.exceptions import BusinessError, ObjectPermissionDenied
from plugin_host.registry import get_enabled_plugins
from plugin_host.request_id import reset_request_id, set_request_id
from plugin_host.theming import (
    THEME_COOKIE_NAME,
    discover_themes,
    reset_current_theme,
    resolve_theme_key,
    set_current_theme,
)

logger = logging.getLogger('plugin_host')


class RequestIdMiddleware:
    """v1.7.5：给每个请求分配 8 位 request_id，写进响应头并供日志 filter 读取。

    位置：`SecurityMiddleware` 之后（最外层之一）——
    这样 500 也在它的 `__call__` 覆盖范围内，响应头一定有号；
    `ExceptionGuardMiddleware` 放在它之内，兜底日志里的 request_id 必然已存在。
    """

    HEADER = 'X-Request-Id'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid.uuid4().hex[:8]
        # 同时挂到请求上：django.request 的 4xx/5xx 日志在中间件返回后才发，
        # 那时 contextvar 已 reset，日志 filter 靠 request.request_id 取号。
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
            response[self.HEADER] = request_id
            return response
        finally:
            reset_request_id(token)


class ExceptionGuardMiddleware:
    """v1.7.5：把容器级业务异常翻译成响应，并保证兜底日志带 request_id。

    判定顺序（`process_exception` 只接得住「视图执行期间」的异常；
    `RequestIdMiddleware` 自身 `__call__` 前段与其它中间件抛的异常不归它管）：
      BusinessError / ObjectPermissionDenied → 记 warning + 400/403
      其它 → `logger.exception` 打全栈后 return None，交回 Django 默认 500 处理
    整个方法体用 try 包住：自身失败只记日志、绝不外抛（否则错误处理器会再炸一次）。
    """

    # JSON 接口错误体（v1.7.5 统一契约）
    JSON_KEYS = ('code', 'message')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def _wants_json(request):
        accept = request.headers.get('Accept', '')
        return request.path.rstrip('/').endswith('/stats') or 'application/json' in accept

    def _error_response(self, request, status, code, message):
        if self._wants_json(request):
            return JsonResponse({'code': code, 'message': message}, status=status)
        if status == 400:
            # message 由模板默认转义（BusinessError 可能夹带用户输入）
            return render(request, '400.html', {'message': message}, status=400)
        # 403 不回显 exception 文本（避免泄漏内部细节）
        return render(request, '403.html', status=403)

    def process_exception(self, request, exception):
        try:
            if isinstance(exception, BusinessError):
                logger.warning('业务校验失败 code=%s msg=%s', exception.code, exception)
                return self._error_response(request, 400, exception.code, exception.message)

            if isinstance(exception, (ObjectPermissionDenied, PermissionDenied)):
                code = getattr(exception, 'code', 'permission_denied')
                logger.warning('拒绝访问 code=%s %s %s',
                               code, request.method, request.get_full_path())
                return self._error_response(request, 403, code, '无权访问该对象')

            # 未预期异常：打全栈（含 request_id），返回 None 交默认 500 处理器渲染 templates/500.html
            logger.exception('未处理异常 %s %s', request.method, request.get_full_path())
            return None
        except Exception:
            # 守卫自身失败：只记日志，绝不外抛，让 Django 走默认 500
            logger.exception('ExceptionGuardMiddleware 自身失败，已降级为默认处理')
            return None


class ThemeMiddleware:
    """按 `oa_theme` Cookie 选择主题；非法值回退 OA_THEME。

    主题在本次请求内通过 contextvar 生效：ThemeLoader 解析模板时读取；
    响应结束后复位，避免线程复用串主题。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = resolve_theme_key(request.COOKIES.get(THEME_COOKIE_NAME))
        request.theme = discover_themes(settings.BASE_DIR)[key]
        token = set_current_theme(key)
        try:
            return self.get_response(request)
        finally:
            reset_current_theme(token)


class DefaultLanguageMiddleware(LocaleMiddleware):
    """默认中文：Cookie（最后设置的语言）有效则用 Cookie，否则固定 LANGUAGE_CODE。

    不跟随 Accept-Language——英文浏览器首次访问保持中文。
    """

    def process_request(self, request):
        valid = {code for code, _ in settings.LANGUAGES}
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang not in valid:
            lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = lang


class PluginRouteGuardMiddleware:
    """插件路由请求级守卫（运行时启停即时生效）。

    URLConf 在启动时静态 include 插件路由，无法按请求刷新；
    本中间件在每个 /plugins/<name>/ 请求上核对运行时开关（get_enabled_plugins），
    已停用插件的请求直接 404，启用后即刻恢复。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith('/plugins/'):
            parts = path.split('/')
            if len(parts) > 2 and parts[2]:
                enabled_names = {name for name, _ in get_enabled_plugins()}
                if parts[2] not in enabled_names:
                    return HttpResponseNotFound('插件已停用')
        return self.get_response(request)
