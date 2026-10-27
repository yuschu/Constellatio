"""容器中间件：主题选择 + 语言默认值 + 插件路由请求级守卫。

v1.5.7：语言中间件归属容器——language 插件停用后仍沿用最后设置的语言。
v1.5.8：主题运行时切换——按 Cookie 选择主题，模板由 ThemeLoader 按请求解析。
"""

from django.conf import settings
from django.http import HttpResponseNotFound
from django.middleware.locale import LocaleMiddleware
from django.utils import translation

from plugin_host.registry import get_enabled_plugins
from plugin_host.theming import (
    THEME_COOKIE_NAME,
    discover_themes,
    reset_current_theme,
    resolve_theme_key,
    set_current_theme,
)


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
