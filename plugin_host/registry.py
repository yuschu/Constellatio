"""插件注册表：OA_PLUGINS 配置驱动，运行时聚合插件元信息。

核心职责：
- register(): 插件在 AppConfig.ready() 中注册 PluginMeta
- get_enabled_plugins(): 按 OA_PLUGINS 配置过滤出已启用且已注册的插件
- get_menus(): 聚合菜单供统一外壳渲染（v0.2 完善 RBAC 过滤）
- plugin_enabled(): 单个插件的启用判定（静态配置 → DB 开关 → 默认启用）
"""

import logging
import time

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

PLUGIN_REGISTRY = {}  # name -> PluginMeta

# 插件开关进程内缓存：默认 30 秒；写操作（PluginSwitch.save/delete）即时失效。
PLUGIN_SWITCH_CACHE_TTL = 30
# 开关表不可读（未迁移 / workspace 停用）时的短暂降级缓存，避免每次请求都打 DB。
PLUGIN_SWITCH_ERROR_TTL = 5

_switch_cache = {'expires': 0.0, 'switches': None}


class PluginMeta:
    """插件契约：每个插件必须提供的字段。"""

    def __init__(self, name, version, title=None, menus=None, permissions=None,
                 urls=None, signals=None, templates=None, app=None):
        self.name = name
        self.version = version
        self.title = title or name          # 展示名（可 gettext_lazy）
        self.menus = menus or []            # [{'label','icon','url'}, ...]
        self.permissions = permissions or []  # ['user_manage', ...]
        self.urls = urls                    # 路由模块路径（可空）
        self.signals = signals or []        # 订阅/发出的信号
        self.templates = templates          # 模板目录名
        self.app = app                      # Django AppConfig 实例


def register(meta: PluginMeta):
    if meta.name in PLUGIN_REGISTRY:
        raise ValueError(f'插件重名: {meta.name}')
    PLUGIN_REGISTRY[meta.name] = meta


def get_plugin_switches():
    """插件 DB 开关快照 {app_key: enabled}，进程内 TTL 缓存。

    只读快照，调用方不得修改；写路径通过 invalidate_plugin_switch_cache() 失效。
    表未迁移 / workspace 停用 / 查询失败时返回空快照（调用方回退静态配置）。

    事务内（TestCase / ATOMIC_REQUESTS）直接读 DB：事务回滚后进程缓存无法感知，
    沿用缓存会让测试之间互相污染；事务外才启用 TTL 缓存。
    """
    from django.db import connection

    use_cache = not connection.in_atomic_block
    if use_cache:
        cached = _switch_cache['switches']
        if cached is not None and time.monotonic() < _switch_cache['expires']:
            return cached

    try:
        from plugins.workspace.models import PluginSwitch
        switches = dict(PluginSwitch.objects.values_list('app_key', 'enabled'))
    except (ImportError, LookupError, OperationalError, ProgrammingError):
        logger.warning('插件开关表不可用，回退静态 OA_PLUGINS 配置', exc_info=True)
        if use_cache:
            _switch_cache['switches'] = {}
            _switch_cache['expires'] = time.monotonic() + PLUGIN_SWITCH_ERROR_TTL
        return {}

    if use_cache:
        _switch_cache['switches'] = switches
        _switch_cache['expires'] = time.monotonic() + PLUGIN_SWITCH_CACHE_TTL
    return switches


def invalidate_plugin_switch_cache():
    """清空开关缓存：PluginSwitch 保存 / 删除后调用（测试也可显式调用）。"""
    _switch_cache['switches'] = None
    _switch_cache['expires'] = 0.0


def _static_plugin_enabled(key):
    """静态 OA_PLUGINS 中的 enabled；插件不在静态配置中返回 None。"""
    for item in getattr(settings, 'OA_PLUGINS', None) or []:
        if item['app'].rsplit('.', 1)[-1] == key:
            return bool(item.get('enabled', True))
    return None


def plugin_enabled(key):
    """单个插件是否启用：DB 开关优先，其次静态 OA_PLUGINS，最后默认 True。

    Provider 插件（如 charts）不在 OA_PLUGINS，同样可被 DB 开关覆盖。
    """
    switches = get_plugin_switches()
    if key in switches:
        return bool(switches[key])
    static = _static_plugin_enabled(key)
    return True if static is None else static


def plugin_counts():
    """(已启用插件数, 已注册插件总数)：工作台与首页统一口径。"""
    switches = get_plugin_switches()
    total = len(PLUGIN_REGISTRY)
    enabled = 0
    for key in PLUGIN_REGISTRY:
        if key in switches:
            enabled += 1 if switches[key] else 0
        else:
            static = _static_plugin_enabled(key)
            enabled += 1 if static is None or static else 0
    return enabled, total


def get_enabled_plugins():
    """按 OA_PLUGINS 顺序返回 (name, meta) 列表。

    workspace 插件提供 DB 运行时开关：有记录以 DB 为准（即时生效），
    无记录回退静态配置；表未迁移/插件停用时回退静态配置。
    """
    switches = get_plugin_switches()
    result = []
    for item in getattr(settings, 'OA_PLUGINS', []):
        key = item['app'].rsplit('.', 1)[-1]
        enabled = switches[key] if key in switches else item.get('enabled', True)
        if not enabled:
            continue
        meta = PLUGIN_REGISTRY.get(key)
        if meta:
            result.append((key, meta))
    return result


def _user_has_perm(user, codename):
    """RBAC 权限判定：统一走 User.has_perm（含超管、全员基线、冻结短路）。"""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return bool(user.has_perm(codename))


def _baseline_perms():
    """全员基线权限码（来自 user 插件；未安装时为空集合）。"""
    try:
        from plugins.user.perms import BASELINE_PERMS
    except ImportError:
        logger.warning('user 插件基线权限不可用', exc_info=True)
        return frozenset()
    return BASELINE_PERMS


def _user_perm_codenames(user):
    """一次查询取用户可用权限码集合，语义对齐 User.has_perm。

    - 未登录 / 冻结 / 停用 → 空集合（全部拒绝）
    - 超管 → None（表示全部放行，无需逐条判定）
    - 其余 → 基线 + 个人权限 + 角色权限的 codename 集合
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return frozenset()
    if getattr(user, 'permission_frozen', False):
        return frozenset()
    if getattr(user, 'is_superuser', False):
        return None
    if not getattr(user, 'is_active', False):
        return frozenset()

    codenames = set(_baseline_perms())
    codenames.update(user.user_permissions.values_list('codename', flat=True))
    codenames.update(
        user.roles.values_list('permissions__codename', flat=True))
    return codenames


def _perm_codename(perm):
    """'app.codename' → 'codename'；裸码原样返回（与 User.has_perm 一致）。"""
    return (perm or '').rsplit('.', 1)[-1]


def get_menus(user, plugins=None):
    """按用户权限过滤菜单：菜单项可声明 perm（如 {'label','icon','url','perm'}），
    无 perm 的菜单登录即可见；有 perm 的按 RBAC 过滤。

    权限集合一次取全，菜单判定只查内存集合，避免逐条 has_perm 的 N+1 查询。
    plugins 可传入已解析的 get_enabled_plugins() 结果，避免同一次请求重复查开关表。
    """
    menus = []
    allowed = _user_perm_codenames(user)
    for name, meta in (get_enabled_plugins() if plugins is None else plugins):
        for menu in meta.menus:
            perm = menu.get('perm')
            if perm and allowed is not None \
                    and _perm_codename(perm) not in allowed:
                continue
            menus.append({**menu, 'plugin': name})
    return menus
