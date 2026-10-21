"""容器中间件：插件路由请求级守卫（运行时启停即时生效）。

URLConf 在启动时静态 include 插件路由，无法按请求刷新；
本中间件在每个 /plugins/<name>/ 请求上核对运行时开关（get_enabled_plugins），
已停用插件的请求直接 404，启用后即刻恢复。
"""

from django.http import HttpResponseNotFound

from plugin_host.registry import get_enabled_plugins


class PluginRouteGuardMiddleware:
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
