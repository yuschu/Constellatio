"""插件注册表：OA_PLUGINS 配置驱动，运行时聚合插件元信息。

核心职责：
- register(): 插件在 AppConfig.ready() 中注册 PluginMeta
- get_enabled_plugins(): 按 OA_PLUGINS 配置过滤出已启用且已注册的插件
- get_menus(): 聚合菜单供统一外壳渲染（v0.2 完善 RBAC 过滤）
- plugin_enabled(): 单个插件的启用判定（静态配置 → DB 开关 → 默认启用）
"""

import logging

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

PLUGIN_REGISTRY = {}  # name -> PluginMeta

class PluginMeta:
    """插件契约：每个插件必须提供的字段。"""

    def __init__(self, name, version, title=None, menus=None, permissions=None,
                 urls=None, signals=None, templates=None, app=None,
                 home_provider=None, builtin=False):
        self.name = name
        self.version = version
        self.title = title or name          # 展示名（可 gettext_lazy）
        self.menus = menus or []            # [{'label','icon','url'}, ...]
        self.permissions = permissions or []  # ['user_manage', ...]
        self.urls = urls                    # 路由模块路径（可空）
        self.signals = signals or []        # 订阅/发出的信号
        self.templates = templates          # 模板目录名
        self.app = app                      # Django AppConfig 实例
        self.home_provider = home_provider  # 可调用对象：request -> HttpResponse；None = 不接管首页
        # v2.2.0：内置插件——随系统提供（语言、认证、账号、组织架构、插件页自身、图表引擎）。
        # 不进插件页清单、界面不可停用（`manage.py plugin_switch` 仍可兜底），
        # 计数也不含它们：插件页说的是「可装可停的业务插件」，不是系统底座。
        self.builtin = bool(builtin)


def register(meta: PluginMeta):
    if meta.name in PLUGIN_REGISTRY:
        raise ValueError(f'插件重名: {meta.name}')
    PLUGIN_REGISTRY[meta.name] = meta


def get_plugin_switches():
    """插件 DB 开关快照 {app_key: enabled}，**每次调用都读表**。

    v1.7.13 删掉了 v1.7.3 引入的进程内 TTL 缓存：`PluginSwitch.save()` 只能清掉
    「处理写操作的那个进程」的缓存，其它 worker 会继续用旧快照 —— 3 worker 下停用插件
    后最多 30 秒内仍可访问（`PluginRouteGuardMiddleware` 正是用它决定是否拦路由）。

    表很小（插件数 × 环境，个位数到十几行）。实测（CaptureQueriesContext 真发请求）每请求查开关表：
    **首页 6 次；插件页 3~4 次**（有图表的页多一次——`charts.chart_switch_enabled` 经 `get_active_chart`
    再查；首页另有 `views:get_enabled_plugins` / `views:plugin_counts` / `workbench` 各 1）。
    成本可忽略；合并这几次查询见 roadmap 待办。
    信号方案在多进程下只清本进程，会把缺陷伪装成已修复；版本号方案需要共享存储，
    每请求至少两次查询，比直接读表更贵 —— 两种方案都**评估**过了（信号方案未实跑），结论是直接删。

    表不可读（首次 migrate 之前 / 表被删 / workspace 库整体不可用）时返回空快照，
    调用方回退静态 OA_PLUGINS。这种状态下每请求一条 warning 是**应该被看见**的；
    要降噪应在启动期检查报错，而不是再造一个进程内状态把延迟藏回来。
    """
    try:
        from plugins.workspace.models import PluginSwitch
        return dict(PluginSwitch.objects.values_list('app_key', 'enabled'))
    except (ImportError, LookupError, OperationalError, ProgrammingError):
        logger.warning('插件开关表不可用，回退静态 OA_PLUGINS 配置', exc_info=True)
        return {}


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


def get_home_provider(user=None, include_disabled=False):
    """返回第一个声明了 home_provider 的插件实现；没有则返回 None。

    默认只取「已启用」的插件；`include_disabled=True` 时连停用的也取——
    v2.2.1 起首页要能在助手插件停用后继续渲染外壳（只关新会话与输入区），
    整页回落看板会把侧栏入口一起换掉，比「关了还能用」更破坏使用现场。
    多个插件同时声明时取 PLUGIN_REGISTRY 注册顺序的第一个并打 warning：
    「谁的首页生效」必须确定，不能随插件加载顺序漂移。
    user 预留给后续按权限过滤首页实现，本版不参与判定。
    """
    providers = []
    for key, meta in PLUGIN_REGISTRY.items():
        if meta.home_provider and (include_disabled or plugin_enabled(key)):
            providers.append((key, meta.home_provider))
    if not providers:
        return None
    if len(providers) > 1:
        logger.warning(
            '多个插件声明了首页接管，按注册顺序取第一个: %s',
            ', '.join(key for key, _ in providers))
    return providers[0][1]


def plugin_counts():
    """(已启用插件数, 插件总数)：工作台与首页统一口径，只算**非内置**插件。

    v2.2.0 起内置插件（语言 / 认证 / 账号 / 组织架构 / 插件页自身 / 图表引擎）
    不进插件页清单，计数跟着走——否则会出现「页面上 7 张卡，KPI 说 13 个插件」
    这种自相矛盾的数字。
    """
    switches = get_plugin_switches()
    visible = [key for key, meta in PLUGIN_REGISTRY.items() if not meta.builtin]
    total = len(visible)
    enabled = 0
    for key in visible:
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
        _collect_menus(menus, name, meta, allowed)
    # v2.0.6：侧栏顺序由菜单自带 order 决定（缺省 100，保持插件注册序）。
    # 让「插件」能钉在「助手」之后，而不必改动 OA_PLUGINS 的加载顺序——
    # 插件注册顺序是启动契约，不该被界面排序反过来绑架。
    menus.sort(key=lambda m: m.get('order', 100))
    return menus


def get_container_menus(user):
    """容器自带的内置菜单（builtin 且不在 OA_PLUGINS）。

    v2.2.1：看板入口从 assistant 的 PluginMeta 挪到容器的 core，
    目的是「停用 AI 助手」不再连带摘掉看板。这类插件不进 OA_PLUGINS，
    也不受 DB 开关管，所以单独出一份、由外壳在渲染菜单时并进去。
    注意只取「静态配置之外」的内置插件：OA_PLUGINS 里的内置插件（组织架构等）
    仍按开关走，否则停用的内置插件会从这里把菜单漏回来。
    """
    menus = []
    allowed = _user_perm_codenames(user)
    static_keys = {
        item['app'].rsplit('.', 1)[-1]
        for item in (getattr(settings, 'OA_PLUGINS', None) or [])
    }
    for name, meta in PLUGIN_REGISTRY.items():
        if meta.builtin and name not in static_keys:
            _collect_menus(menus, name, meta, allowed)
    return menus


def _collect_menus(menus, name, meta, allowed):
    """把单个插件的菜单按 RBAC 过滤后并入 menus（贡献者姓名记在 plugin 字段）。"""
    for menu in meta.menus:
        perm = menu.get('perm')
        if perm and allowed is not None \
                and _perm_codename(perm) not in allowed:
            continue
        menus.append({**menu, 'plugin': name})
