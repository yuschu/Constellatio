"""插件视图权限准入（v1.5.4）。

所有受控插件视图统一使用 require_perm：
- 未登录 → 登录页（login_required）
- 已登录但无权限码 → 工作台（index）

判定统一走 User.has_perm（含全员基线权限与权限冻结短路）。
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def require_perm(codename):
    """插件权限装饰器：未登录 → 登录页；无权限码 → 工作台。"""
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(codename):
                return redirect('index')
            return view(request, *args, **kwargs)
        return wrapper
    return deco
