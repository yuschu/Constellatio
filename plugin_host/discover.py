"""插件自动发现与注册校验。

各插件 AppConfig.ready() 调用 registry.register() 注册自身；
容器在自身 ready()（Django 全部 app 就绪后）统一校验注册表，
拦截权限码冲突等问题。
"""

from .registry import PLUGIN_REGISTRY


def check_registry():
    """注册表完整性校验：权限码冲突即启动失败。"""
    seen = set()
    for meta in PLUGIN_REGISTRY.values():
        for perm in meta.permissions:
            if perm in seen:
                raise ValueError(f'权限码冲突: {perm}')
            seen.add(perm)
