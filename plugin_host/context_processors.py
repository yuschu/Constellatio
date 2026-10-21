"""容器上下文处理器：向模板注入插件聚合菜单。"""

from .registry import get_menus


def menus(request):
    if request.user.is_authenticated:
        return {'menus': get_menus(request.user)}
    return {'menus': []}
