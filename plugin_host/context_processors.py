"""容器上下文处理器：向模板注入插件聚合菜单（含当前 Tab 高亮）。"""

from .registry import get_enabled_plugins, get_menus


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
    """注入菜单与本次请求实际启用的插件名。

    v1.5.7：`plugins_enabled` 供外壳按插件启停隐藏入口
    （language 停用 → 不渲染语言表单；auth 停用 → 不渲染登录/登出链接）。
    """
    plugins = get_enabled_plugins()
    enabled = {name for name, _ in plugins}
    if request.user.is_authenticated:
        menu_items = _mark_active(get_menus(request.user, plugins), request.path)
    else:
        menu_items = []
    return {'menus': menu_items, 'plugins_enabled': enabled}
