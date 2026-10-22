"""主题插件发现：themes/<key>/theme.json → ThemeMeta。

设计要点：
- 主题是目录 + 清单，不再要求是 Django app；
- 启动时只读清单，不做运行时热切换（改 OA_THEME 后重启）；
- 当前主题的 templates / static 会写入 settings 的 TEMPLATES.DIRS / STATICFILES_DIRS。
"""

import json
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class ThemeMeta:
    key: str
    name: str
    version: str
    root: Path
    templates: Path
    static: Path


def discover_themes(base_dir: Path) -> dict[str, ThemeMeta]:
    """扫描 themes/*/theme.json，返回 {key: ThemeMeta}。"""
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
