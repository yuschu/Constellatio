"""容器上下文处理器：插件菜单（含当前 Tab 高亮）、启用插件名、主题列表、图表引擎。"""

import hashlib
import logging
from pathlib import Path

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

# 首页自己承载的面板入口：这三条在首页内切换（/?panel=…），业务页侧栏不再
# 重复列一遍。插件页已移回业务页「功能」侧栏首位，不再由首页承接；公告也改由
# 首页 `?panel=notice` 承载，所以公告不再出现在业务页「功能」侧栏。
HOME_PANEL_URLS = (
    '/plugins/attendance/',   # 考勤
    '/plugins/notice/',       # 公告
    '/dashboard/',            # 看板
)


def color_mode(request):
    """注入当前配色模式；非法或缺失回退浅色。

    外壳把 `color_mode` 写进 `<html data-color-mode>`，CSS 只按这个属性
    切换 alias 取值，不改任何规则块。
    """
    stored = request.COOKIES.get(COLOR_MODE_COOKIE)
    return {'color_mode': stored if stored in COLOR_MODES else DEFAULT_COLOR_MODE}


def _shortcut_id(url):
    """v2.2.16：快捷键覆盖用入口 URL 生成稳定 ID。

    旧实现按 `quick.{序号}` 存储，但首页「快速操作」来自 primary + common，
    业务页来自侧栏菜单，两边顺序不同：同一个 `quick.1` 在首页是「考勤」、
    在业务页是「插件」。改一次键会串到别的入口，所以 ID 必须绑定入口本身。
    """
    path = (url or '/').strip()
    if path.startswith('/?panel='):
        return 'panel.' + path.split('=', 1)[1]
    path = path.split('?', 1)[0].strip('/')
    return (path or 'home').replace('/', '.')


def _annotate_shortcut_ids(menus):
    for menu in menus:
        menu['shortcut_id'] = _shortcut_id(menu.get('url'))
    return menus


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
        menu_items = _annotate_shortcut_ids(_mark_active(
            sorted(
                get_menus(request.user, plugins) + get_container_menus(request.user),
                key=lambda m: m.get('order', 100)),
            request.path))
    else:
        menu_items = []
    # v2.1.0：业务页侧栏不再展示首页已承载的面板入口（考勤 / 看板）。
    # 插件入口已回到业务页「功能」侧栏首位，因此不再参与这里的过滤。
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

# v2.2.15：静态资源版本戳改成内容哈希。
# 旧实现取 mtime 最大值；Docker `COPY . .` 会保留源文件 mtime，重建后戳不变，
# 浏览器继续拿着同名旧 CSS/JS —— 部署后看起来像"容器还是老版本"。
# 内容哈希与 mtime 无关，文件内容一变，?v= 必变。
_ASSETS_VERSION = None
_ASSET_STAMP_FILES = (
    'plugin_host/static/css/ds-panels.css',
    'themes/corporate-clean/static/themes/corporate-clean/css/corporate-clean.css',
    'plugins/assistant/static/assistant/css/assistant.css',
    'plugin_host/static/js/ds-shell.js',
    'plugin_host/static/js/shortcuts.js',
    'plugin_host/static/js/confirm.js',
    'plugin_host/static/js/dashboard-range.js',
    'plugin_host/static/js/rail-boot.js',
    'plugin_host/static/js/home-panels.js',
    'themes/corporate-clean/static/themes/corporate-clean/js/home.js',
)


def _build_assets_version(base_dir=None, files=None):
    """对固定资源清单做内容哈希；文件缺失也参与哈希，清单顺序保持稳定。"""
    base = Path(base_dir or settings.BASE_DIR)
    digest = hashlib.sha256()
    for rel in files or _ASSET_STAMP_FILES:
        digest.update(rel.encode('utf-8'))
        digest.update(b'\0')
        try:
            payload = (base / rel).read_bytes()
        except OSError:
            digest.update(b'<missing>')
        else:
            digest.update(hashlib.sha256(payload).digest())
        digest.update(b'\0')
    return digest.hexdigest()[:16]


def assets(request):
    """注入静态资源版本戳（v2.2.15），模板里写成 ?v={{ assets_version }}。"""
    global _ASSETS_VERSION
    if _ASSETS_VERSION is None:
        _ASSETS_VERSION = _build_assets_version()
    return {'assets_version': _ASSETS_VERSION}
