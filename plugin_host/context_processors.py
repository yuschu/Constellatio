"""容器上下文处理器：插件菜单（含当前 Tab 高亮）、启用插件名、主题列表、图表引擎。"""

import logging

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from .charts import get_active_chart
from .registry import get_container_menus, get_enabled_plugins, get_menus
from .theming import discover_themes

logger = logging.getLogger(__name__)

# v2.0：全站深浅模式（首页与业务页共用同一个 Cookie，切换任一页面全站跟随）
COLOR_MODE_COOKIE = 'oa_color_mode'
COLOR_MODES = ('light', 'dark')
DEFAULT_COLOR_MODE = 'light'

# v2.1.0：主页自己承载的面板入口（顺序即首页侧栏顺序）。
# 这三条在首页内切换（/?panel=…），业务页侧栏不再重复列一遍——
# 同一入口出现在两套导航里，用户在业务页永远不知道该点哪一个。
HOME_PANEL_URLS = (
    '/plugins/attendance/',   # 考勤
    '/plugins/workspace/',    # 插件
    '/dashboard/',            # 看板
)


def color_mode(request):
    """注入当前配色模式；非法或缺失回退浅色。

    外壳把 `color_mode` 写进 `<html data-color-mode>`，CSS 只按这个属性
    切换 alias 取值，不改任何规则块。
    """
    stored = request.COOKIES.get(COLOR_MODE_COOKIE)
    return {'color_mode': stored if stored in COLOR_MODES else DEFAULT_COLOR_MODE}


def _mark_active(menus, path):
    """v1.5.5：当前路径命中菜单则标记 active（详情页按前缀归属父菜单）。

    同一前缀下有更精确匹配（如 /attendance/records/ 与 /attendance/）时，
    只高亮最精确的那一项，避免同时高亮两个 Tab。
    v2.0.0：同一个 URL 只让第一个菜单高亮——首页接管后「助手」与旧「工作台」
    都指向 /，不能同时亮两个。
    """
    bases = [(menu.get('url') or '/').rstrip('/') or '/' for menu in menus]
    exact_hit = path.rstrip('/') in bases or path == '/'
    claimed = set()
    for menu, base in zip(menus, bases, strict=False):
        if path == '/':
            active = base == '/'
        elif base == path.rstrip('/'):
            active = True
        else:
            active = (not exact_hit) and path.startswith(base + '/')
        if active and base in claimed:
            active = False
        if active:
            claimed.add(base)
        menu['active'] = active
    return menus


def menus(request):
    """注入菜单与本次请求实际启用的插件名。

    v1.5.7：`plugins_enabled` 供外壳按插件启停隐藏入口
    （language 停用 → 不渲染语言表单；auth 停用 → 不渲染登录/登出链接）。
    """
    plugins = get_enabled_plugins()
    enabled = {name for name, _ in plugins}
    if request.user.is_authenticated:
        # v2.2.1：容器自带的内置菜单（看板）与插件菜单合并后再排序——
        # 停用 AI 助手不该把看板入口一起摘掉，而看板的来源已从 assistant 挪到 core。
        menu_items = _mark_active(
            sorted(
                get_menus(request.user, plugins) + get_container_menus(request.user),
                key=lambda m: m.get('order', 100)),
            request.path)
    else:
        menu_items = []
    # v2.1.0：业务页侧栏不再展示首页已承载的面板入口（考勤 / 插件 / 看板），
    # 首页侧栏仍用未过滤的 menus。
    sidebar_items = [
        menu for menu in menu_items
        if (menu.get('url') or '/') not in HOME_PANEL_URLS
    ]
    return {
        'menus': menu_items,
        'sidebar_menus': sidebar_items,
        'plugins_enabled': enabled,
    }


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
    except (ImportError, LookupError, OperationalError, ProgrammingError):
        logger.warning('站内信未读数不可用，降级为 0', exc_info=True)
        count = 0
    return {'notify_unread': count}

# v2.1.5：静态资源版本戳。
# 容器重建后 CSS 仍是同名文件，浏览器对同 URL 的缓存不会失效 ——
# 页面上给静态链接带 ?v=<mtime>，重建后 URL 变化即强制重新拉取。
_ASSETS_VERSION = None
_ASSET_STAMP_FILES = (
    'themes/corporate-clean/static/themes/corporate-clean/css/corporate-clean.css',
    'plugin_host/static/js/ds-shell.js',
    'plugin_host/static/js/shortcuts.js',
    'plugin_host/static/js/confirm.js',
    'plugin_host/static/js/dashboard-range.js',
    'themes/corporate-clean/static/themes/corporate-clean/js/home.js',
)


def assets(request):
    """注入静态资源版本戳（v2.1.5），模板里写成 ?v={{ assets_version }}。"""
    global _ASSETS_VERSION
    if _ASSETS_VERSION is None:
        stamp = 0
        for rel in _ASSET_STAMP_FILES:
            try:
                stamp = max(stamp, int((settings.BASE_DIR / rel).stat().st_mtime))
            except OSError:
                continue
        _ASSETS_VERSION = str(stamp)
    return {'assets_version': _ASSETS_VERSION}
