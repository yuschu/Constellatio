"""认证后端契约校验（v1.7.7）。

契约（缺一条都 `ImproperlyConfigured`，启动即吵，不静默降级）：
1. 能 import；
2. 是 `BaseBackend` 子类；
3. **覆盖了 `authenticate`**（`BaseBackend.authenticate` 直接返回 None，等于永不登录）；
4. **覆盖了 `get_user`**（`BaseBackend.get_user` 返回 None，会话在下一请求就失效——
   表现为「登录成功但刷新即掉线」，比启动报错难查得多）。

空列表放行（只保留 `ModelBackend`），否则新环境第一次 `migrate` 就死在校验里。
"""

from importlib import import_module

from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import ImproperlyConfigured


def _import_backend_class(path):
    module_path, _, class_name = str(path).rpartition('.')
    if not module_path or not class_name:
        raise ImproperlyConfigured(
            f'认证后端路径非法（应为 dotted path，如 app.mod.Class）: {path!r}')
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise ImproperlyConfigured(f'认证后端无法导入: {path}: {exc}') from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise ImproperlyConfigured(f'认证后端模块 {module_path} 里没有 {class_name}') from exc


def validate_auth_backends(paths):
    """校验并实例化 Provider 列表；返回 backend 实例（空列表返回空列表，不报错）。"""
    backends = []
    for path in paths or []:
        cls = _import_backend_class(path)
        if not (isinstance(cls, type) and issubclass(cls, BaseBackend)):
            raise ImproperlyConfigured(
                f'认证后端必须是 BaseBackend 子类: {path}')
        if getattr(cls, 'authenticate', None) is BaseBackend.authenticate:
            raise ImproperlyConfigured(
                f'认证后端必须覆盖 authenticate(): {path}')
        if getattr(cls, 'get_user', None) is BaseBackend.get_user:
            raise ImproperlyConfigured(
                f'认证后端必须覆盖 get_user()（否则登录后下一个请求就掉线）: {path}')
        backends.append(cls())
    return backends
