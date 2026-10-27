"""插件自动发现与注册校验。

各插件 AppConfig.ready() 调用 registry.register() 注册自身；
注册表完整性校验挂在 Django 系统检查（checks）上，在全部 app 就绪后由
`manage.py check` / test / runserver 触发——plugin_host 在 INSTALLED_APPS
中排在业务插件之前，若在自身 ready() 里直接校验，注册表几乎为空，等于空转。

测试可显式调用 assert_registry_ok()。
"""

from django.core.checks import Error, register

from .registry import PLUGIN_REGISTRY


@register()
def check_registry(app_configs=None, **kwargs):
    """系统检查（plugin_host.E001）：插件权限码全局唯一，冲突返回 Error 列表。"""
    seen = {}
    errors = []
    for name, meta in PLUGIN_REGISTRY.items():
        for perm in meta.permissions:
            if perm in seen:
                errors.append(Error(
                    f'插件权限码冲突: {perm}',
                    hint=f'{seen[perm]} 与 {name} 都声明了权限码 {perm}',
                    id='plugin_host.E001',
                ))
            else:
                seen[perm] = name
    return errors


def assert_registry_ok():
    """显式校验注册表；有冲突时抛 ValueError（测试用）。"""
    errors = check_registry()
    if errors:
        raise ValueError('; '.join(error.msg for error in errors))
