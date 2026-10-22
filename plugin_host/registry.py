"""插件注册表：OA_PLUGINS 配置驱动，运行时聚合插件元信息。

核心职责：
- register(): 插件在 AppConfig.ready() 中注册 PluginMeta
- get_enabled_plugins(): 按 OA_PLUGINS 配置过滤出已启用且已注册的插件
- get_menus(): 聚合菜单供统一外壳渲染（v0.2 完善 RBAC 过滤）
"""

from django.conf import settings

PLUGIN_REGISTRY = {}  # name -> PluginMeta


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


def get_enabled_plugins():
    """按 OA_PLUGINS 顺序返回 (name, meta) 列表。

    workspace 插件提供 DB 运行时开关：有记录以 DB 为准（即时生效），
    无记录回退静态配置；表未迁移/插件停用时回退静态配置。
    """
    switches = {}
    try:
        from plugins.workspace.models import PluginSwitch
        switches = {s.app_key: s.enabled for s in PluginSwitch.objects.all()}
    except Exception:          # 表未迁移 / workspace 插件停用
        pass
    result = []
    for item in getattr(settings, 'OA_PLUGINS', []):
        key = item['app'].rsplit('.', 1)[-1]
        enabled = switches.get(key, item.get('enabled', True))   # DB 优先
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


def get_menus(user):
    """按用户权限过滤菜单：菜单项可声明 perm（如 {'label','icon','url','perm'}），
    无 perm 的菜单登录即可见；有 perm 的按 RBAC 过滤。"""
    menus = []
    for name, meta in get_enabled_plugins():
        for menu in meta.menus:
            perm = menu.get('perm')
            if perm and not _user_has_perm(user, perm):
                continue
            menus.append({**menu, 'plugin': name})
    return menus
