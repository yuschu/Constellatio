"""图表引擎插件发现与运行时选择：charts/<key>/chart.json → ChartMeta / ChartRenderer。

与主题同模型（见 docs/plugin-dev-theme.md）：
- 图表引擎 = 目录 + 清单，不是 Django app，不进 INSTALLED_APPS、不写迁移；
- 启动时扫描清单；清单不可解析 / 字段缺失 / 渲染器不合契约 → ImproperlyConfigured（失败要吵）；
- `OA_CHARTS` 选择默认引擎；空 / none / off → 停用，业务页面降级为表格；
- 未知 key → 记 warning 并降级，不让页面 500。

业务视图只依赖本模块的 `payload()`，不 import 任何具体引擎。
"""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static

logger = logging.getLogger(__name__)

# 视为「停用图表引擎」的配置值（大小写不敏感）
DISABLED_KEYS = {'', 'none', 'off', 'false', '0'}

# 清单里必须声明的字段
REQUIRED_FIELDS = ('name', 'version', 'renderer', 'static', 'asset')


@dataclass(frozen=True)
class ChartMeta:
    """图表 Provider 元信息（key / name / version / static / asset，与 ThemeMeta 同模型）。"""

    key: str
    name: str
    version: str
    root: Path          # charts/<key>/
    static: Path        # charts/<key>/<static>/（进 STATICFILES_DIRS）
    asset: str          # 相对 static 的引擎脚本（走 static() 出 URL）
    adapter: str        # 相对 static 的适配脚本；可为空字符串
    renderer_path: str  # 渲染器类路径（dotted）


class ChartRenderer:
    """图表渲染器契约：Provider 只需实现 option()，容器统一组装 payload。

    - categories: 类目轴（字符串列表）
    - series: [{'key','name','data','type'?}, ...]，name 已按当前语言本地化
    - option(): 返回该引擎可直接消费的字典（必须 JSON 可序列化）
    """

    def __init__(self, meta: ChartMeta):
        self.meta = meta

    @property
    def key(self):
        return self.meta.key

    @property
    def name(self):
        return self.meta.name

    @property
    def version(self):
        return self.meta.version

    @property
    def script_url(self):
        return static(self.meta.asset)

    @property
    def adapter_url(self):
        return static(self.meta.adapter) if self.meta.adapter else ''

    def option(self, *, categories=None, series=None, title='', kind='cartesian',
               compact=False):
        raise NotImplementedError('图表 Provider 必须实现 option()')

    def payload(self, *, categories=None, series=None, title='', kind='cartesian',
                compact=False, link='', alert=False):
        """容器与业务视图只消费这个结构。

        kind: cartesian（柱 / 线，由 series.type 决定）、pie（环形）、gauge（进度环）；
        compact: 迷你图（隐藏坐标轴）；link: 图表点击跳转；alert: 告警色。
        """
        return {
            'engine': self.meta.key,
            'option': self.option(
                categories=categories, series=series, title=title,
                kind=kind, compact=compact),
            'link': link,
            'alert': bool(alert),
        }


@lru_cache(maxsize=8)
def discover_charts(base_dir) -> dict[str, ChartMeta]:
    """扫描 charts/*/chart.json，返回 {key: ChartMeta}（进程内缓存）。"""
    base = Path(base_dir)
    charts: dict[str, ChartMeta] = {}
    for manifest in sorted((base / 'charts').glob('*/chart.json')):
        key = manifest.parent.name
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImproperlyConfigured(f'图表清单无法解析: {manifest}: {exc}') from exc
        for field in REQUIRED_FIELDS:
            if not data.get(field):
                raise ImproperlyConfigured(f'图表 {key} 缺少字段: {field}')

        static_dir = (manifest.parent / data['static']).resolve()
        if not static_dir.is_dir():
            raise ImproperlyConfigured(f'图表 {key} 缺少静态目录: {static_dir}')
        asset = (static_dir / data['asset']).resolve()
        if static_dir not in asset.parents:
            raise ImproperlyConfigured(f'图表 {key} 的 asset 越出静态目录: {data["asset"]}')
        if not asset.is_file():
            raise ImproperlyConfigured(f'图表 {key} 缺少引擎脚本: {asset}')

        adapter = (static_dir / data['adapter']).resolve() if data.get('adapter') else None
        if adapter is not None:
            if static_dir not in adapter.parents:
                raise ImproperlyConfigured(f'图表 {key} 的 adapter 越出静态目录')
            if not adapter.is_file():
                raise ImproperlyConfigured(f'图表 {key} 缺少适配脚本: {adapter}')

        charts[key] = ChartMeta(
            key=key,
            name=data['name'],
            version=data['version'],
            root=manifest.parent,
            static=static_dir,
            asset=asset.relative_to(static_dir).as_posix(),
            adapter=adapter.relative_to(static_dir).as_posix() if adapter else '',
            renderer_path=data['renderer'],
        )
    return charts


_RENDERERS: dict[str, ChartRenderer] = {}


def get_renderer(meta: ChartMeta) -> ChartRenderer:
    """按清单声明加载渲染器（进程内复用实例）。"""
    renderer = _RENDERERS.get(meta.key)
    if renderer is not None:
        return renderer

    module_path, _, class_name = meta.renderer_path.rpartition('.')
    if not module_path:
        raise ImproperlyConfigured(
            f'图表 {meta.key} 的 renderer 必须是带模块的类路径: {meta.renderer_path}')
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f'图表 {meta.key} 的 renderer 无法导入: {meta.renderer_path}: {exc}') from exc
    renderer_class = getattr(module, class_name, None)
    if not isinstance(renderer_class, type) or not issubclass(renderer_class, ChartRenderer):
        raise ImproperlyConfigured(
            f'图表 {meta.key} 的 renderer 不是 ChartRenderer 子类: {meta.renderer_path}')

    renderer = renderer_class(meta)
    _RENDERERS[meta.key] = renderer
    return renderer


def chart_switch_enabled():
    """workspace 运行时开关（v1.6.1）：与 registry.plugin_enabled 同一口径。

    DB 优先、无记录默认启用；表未迁移 / workspace 停用由 registry 统一降级。
    """
    from plugin_host.registry import plugin_enabled
    return plugin_enabled('charts')


def get_active_chart():
    """当前请求应使用的图表渲染器；停用 / 未知一律返回 None（调用方降级为表格）。"""
    if not chart_switch_enabled():
        return None
    key = getattr(settings, 'OA_CHARTS', 'echarts')
    key = (key or '').strip()
    if key.lower() in DISABLED_KEYS:
        return None
    meta = discover_charts(settings.BASE_DIR).get(key)
    if meta is None:
        logger.warning('未知图表引擎 OA_CHARTS=%r，已降级为表格', key)
        return None
    return get_renderer(meta)
