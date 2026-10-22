"""容器上下文处理器：向模板注入插件聚合菜单（含当前 Tab 高亮）。"""

from .registry import get_menus


def _mark_active(menus, path):
    """v1.5.5：当前路径命中菜单则标记 active（详情页按前缀归属父菜单）。

    同一前缀下有更精确匹配（如 /attendance/records/ 与 /attendance/）时，
    只高亮最精确的那一项，避免同时高亮两个 Tab。
    """
    bases = [(menu.get('url') or '/').rstrip('/') or '/' for menu in menus]
    exact_hit = path.rstrip('/') in bases or path == '/'
    for menu, base in zip(menus, bases):
        if path == '/':
            menu['active'] = base == '/'
        elif base == path.rstrip('/'):
            menu['active'] = True
        else:
            menu['active'] = (not exact_hit) and path.startswith(base + '/')
    return menus


def menus(request):
    if request.user.is_authenticated:
        return {'menus': _mark_active(get_menus(request.user), request.path)}
    return {'menus': []}
