"""auth 插件：统一登录 / 登出（认证后端走 Django auth，可插拔）。

v1.7.1（P1-14）：登录失败计数限流——同一「用户名 + 来源 IP」在窗口内
连续失败达到阈值后，即使密码正确也先拒绝，避免在线爆破。
"""

import hashlib

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.shortcuts import redirect, render
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


def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')

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
                return redirect('index')
            _record_failure(request, username)
            error = _('用户名或密码错误')

    # 失败时回填用户名；密码出于安全不回填
    return render(request, 'login.html', {'error': error, 'username': username})


def logout_view(request):
    logout(request)
    return redirect('index')


def password_reset_notice(request):
    """密码重置占位页：v1.5 只提供入口，不发送邮件、不伪造重置。"""
    return render(request, 'auth/password_reset_notice.html')
