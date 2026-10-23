"""容器中间件：语言默认值 + 插件路由请求级守卫。

语言中间件归属容器（v1.5.7）：language 插件改为普通可停用插件后，
默认中文与实际语言偏好仍由容器生效——停用插件只收走切换入口，不重置语言。
"""

from django.conf import settings
from django.http import HttpResponseNotFound
from django.middleware.locale import LocaleMiddleware
from django.utils import translation

from plugin_host.registry import get_enabled_plugins


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
