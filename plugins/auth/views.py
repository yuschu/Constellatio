"""auth 插件：统一登录 / 登出（认证后端走 Django auth，可插拔）。

v1.7.1（P1-14）：登录失败计数限流——同一「用户名 + 来源 IP」在窗口内
连续失败达到阈值后，即使密码正确也先拒绝，避免在线爆破。
"""

import hashlib

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

# 失败阈值与窗口（秒）：5 次 / 15 分钟
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW = 900


def _client_ip(request):
    """限流维度取 REMOTE_ADDR：不信任可伪造的 X-Forwarded-For。

    若部署在反代之后需要按真实客户端计数，应在反代侧改写 REMOTE_ADDR
    （gunicorn --forwarded-allow-ips + ProxyFix），而不是在这里读请求头。
    """
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _fail_cache_key(request, username):
    """失败计数键：用户名 + IP 一起哈希，避免明文用户名进缓存键。"""
    raw = f'{(username or "").lower()}|{_client_ip(request)}'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]
    return f'auth:login-fail:{digest}'


def _is_locked(request, username):
    return (cache.get(_fail_cache_key(request, username)) or 0) >= LOGIN_FAIL_LIMIT


def _record_failure(request, username):
    key = _fail_cache_key(request, username)
    failures = (cache.get(key) or 0) + 1
    cache.set(key, failures, LOGIN_FAIL_WINDOW)
    return failures


def _next_target(request):
    """v1.7.4 收尾：取登录后要回跳的地址（POST 优先，其次 GET）。

    只返回同站地址；外站与协议相对 URL（`//evil.com`）一律丢弃返回空串。
    校验口径与 Django `LoginView` 的 `SuccessURLAllowedHostsMixin` 一致。
    """
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return ''


def _redirect_after_login(request):
    """登录成功（或已登录用户访问登录页）后：有合法 next 就回原页，否则回工作台。"""
    target = _next_target(request)
    return redirect(target) if target else redirect('index')


@login_not_required        # v1.7.4：匿名入口（否则 LoginRequiredMiddleware 造成无限重定向）
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_after_login(request)

    error = None
    username = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if _is_locked(request, username):
            error = _('尝试次数过多，请稍后再试')
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                cache.delete(_fail_cache_key(request, username))
                login(request, user)
                return _redirect_after_login(request)
            _record_failure(request, username)
            error = _('用户名或密码错误')

    # 失败时回填用户名；密码出于安全不回填。
    # next 必须传进上下文，否则模板里的隐藏域渲染成空串、回跳形同虚设（v1.7.4 收尾）。
    return render(request, 'login.html', {
        'error': error,
        'username': username,
        'next': _next_target(request),
    })


@login_not_required        # v1.7.4：未登录点「退出」不该被跳去登录页
def logout_view(request):
    logout(request)
    return redirect('index')


@login_not_required        # v1.7.4：登录页「忘记密码」入口，匿名可达
def password_reset_notice(request):
    """密码重置占位页：v1.5 只提供入口，不发送邮件、不伪造重置。"""
    return render(request, 'auth/password_reset_notice.html')
