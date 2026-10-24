"""容器上下文处理器：插件菜单（含当前 Tab 高亮）、启用插件名、主题列表、图表引擎。"""

from django.conf import settings

from .charts import get_active_chart
from .registry import get_enabled_plugins, get_menus
from .theming import discover_themes


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


def themes(request):
    """注入可选主题与当前主题（v1.5.8 运行时切换，功能区与任一页面可用）。"""
    items = [(key, meta.name) for key, meta in discover_themes(settings.BASE_DIR).items()]
    current = getattr(getattr(request, 'theme', None), 'key', settings.OA_THEME)
    return {'themes': items, 'current_theme': current}


def charts(request):
    """注入当前图表渲染器（v1.6）；停用 / 未知 Provider 时为 None，模板降级为表格。"""
    return {'chart': get_active_chart()}


def notifications(request):
    """注入站内信未读数（v1.7.0）；未登录 / 插件停用 / 表未迁移时为 0。"""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'notify_unread': 0}
    try:
        from plugins.notify.models import Notification
        count = Notification.objects.filter(
            recipient=request.user, is_read=False).count()
    except Exception:
        count = 0
    return {'notify_unread': count}
