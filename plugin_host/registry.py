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

    def __init__(self, name, version, menus=None, permissions=None,
                 urls=None, signals=None, templates=None, app=None):
        self.name = name
        self.version = version
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
    """按 OA_PLUGINS 顺序返回 (name, meta) 列表（仅已启用且已注册）。"""
    result = []
    for item in getattr(settings, 'OA_PLUGINS', []):
        if not item.get('enabled'):
            continue
        name = item['app'].rsplit('.', 1)[-1]
        meta = PLUGIN_REGISTRY.get(name)
        if meta:
            result.append((name, meta))
    return result


def get_menus(user):
    """按用户权限过滤菜单；v0.1 登录即可见，v0.2 接入 RBAC 精细过滤。"""
    menus = []
    for name, meta in get_enabled_plugins():
        for menu in meta.menus:
            menus.append({**menu, 'plugin': name})
    return menus
