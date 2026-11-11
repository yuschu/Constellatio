"""插件视图权限准入（v1.5.4；v1.7.9 改语义：已登录但无权限 → 403）。

所有受控插件视图统一使用 require_perm：
- 未登录 → 登录页（`@login_required`，302 + next）；`LoginRequiredMiddleware`（v1.7.4）在视图之前
  已经拦掉匿名请求，所以这里不需要再判 `is_authenticated`；
- 已登录但无权限码 → `raise ObjectPermissionDenied` → `ExceptionGuardMiddleware` 渲染
  `403.html`（HTML）或 `{code,message}`（JSON，判据在中间件的 `_wants_json` 里，不在这里重复）。

判定统一走 User.has_perm（含全员基线权限与权限冻结短路）。

v1.7.9 变更：原先是 `redirect('index')`（302 回工作台）。改成 403 的收益是「用户知道自己是被
权限拦下的」；未登录的 302 语义完全不动。
"""

from functools import wraps

from django.contrib.auth.decorators import login_required

from plugin_host.exceptions import ObjectPermissionDenied


def require_perm(codename):
    """插件权限装饰器：未登录 → 登录页(302)；已登录无权限码 → 403。"""
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(codename):
                # 只 raise，不判 JSON：是不是 JSON 由 ExceptionGuardMiddleware._wants_json 决定
                raise ObjectPermissionDenied('无权访问该功能')
            return view(request, *args, **kwargs)
        return wrapper
    return deco
