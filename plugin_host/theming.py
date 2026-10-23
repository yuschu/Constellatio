"""主题插件发现与运行时切换：themes/<key>/theme.json → ThemeMeta。

设计要点：
- 主题是目录 + 清单，不要求是 Django app；
- 启动时校验 OA_THEME（未知主题直接失败）；
- v1.5.8：支持运行时切换——`ThemeMiddleware` 按 Cookie 选择当前主题，
  `ThemeLoader` 按当前主题解析 templates（默认 OA_THEME，请求内由 Cookie 覆盖）；
- 两套主题的 static 都进 STATICFILES_DIRS，切换后 CSS 可用。
"""

import contextvars
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template.loaders.filesystem import Loader as FileSystemLoader

# 主题选择 Cookie（v1.5.8）；未设置/非法时回退 settings.OA_THEME
THEME_COOKIE_NAME = 'oa_theme'
_THEME_KEY = contextvars.ContextVar('oa_theme_key', default=None)


@dataclass(frozen=True)
class ThemeMeta:
    key: str
    name: str
    version: str
    root: Path
    templates: Path
    static: Path


@lru_cache(maxsize=8)
def discover_themes(base_dir: Path) -> dict[str, ThemeMeta]:
    """扫描 themes/*/theme.json，返回 {key: ThemeMeta}（进程内缓存）。"""
    themes = {}
    for manifest in sorted((base_dir / 'themes').glob('*/theme.json')):
        key = manifest.parent.name
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImproperlyConfigured(f'主题清单无法解析: {manifest}: {exc}') from exc
        for field in ('name', 'version', 'templates', 'static'):
            if not data.get(field):
                raise ImproperlyConfigured(f'主题 {key} 缺少字段: {field}')
        root = manifest.parent
        templates = (root / data['templates']).resolve()
        static = (root / data['static']).resolve()
        if not (templates / 'base.html').is_file():
            raise ImproperlyConfigured(f'主题 {key} 缺少 templates/base.html')
        if not static.is_dir():
            raise ImproperlyConfigured(f'主题 {key} 缺少 static 目录')
        themes[key] = ThemeMeta(
            key=key,
            name=data['name'],
            version=data['version'],
            root=root,
            templates=templates,
            static=static,
        )
    return themes


def get_theme(base_dir: Path, key: str) -> ThemeMeta:
    """取指定主题；未知主题直接启动失败，不静默回退。"""
    themes = discover_themes(base_dir)
    if key not in themes:
        available = ', '.join(sorted(themes)) or '(none)'
        raise ImproperlyConfigured(f'未知主题 OA_THEME={key!r}；可用: {available}')
    return themes[key]


def resolve_theme_key(cookie_key, base_dir=None):
    """Cookie → 合法主题 key；非法或缺失回退 OA_THEME（再兜底第一个可用主题）。"""
    base_dir = base_dir or settings.BASE_DIR
    themes = discover_themes(base_dir)
    if cookie_key in themes:
        return cookie_key
    if settings.OA_THEME in themes:
        return settings.OA_THEME
    return next(iter(themes))


def current_theme_key(base_dir=None):
    """当前请求的主题 key；请求外（shell / 测试）回退 OA_THEME。"""
    return _THEME_KEY.get() or resolve_theme_key(None, base_dir)


def set_current_theme(key: str):
    """设置本次请求的主题，返回用于恢复的 token。"""
    return _THEME_KEY.set(key)


def reset_current_theme(token):
    _THEME_KEY.reset(token)


class ThemeLoader(FileSystemLoader):
    """按当前请求主题解析 templates 目录（命中不到时由后续 loader 兜底 app 模板）。"""

    def get_dirs(self):
        theme = get_theme(settings.BASE_DIR, current_theme_key())
        return [str(theme.templates)]
