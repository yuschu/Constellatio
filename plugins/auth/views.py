"""auth 插件：统一登录 / 登出（认证后端走 Django auth，可插拔）。"""

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _


def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')

    error = None
    username = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        error = _('用户名或密码错误')

    # 失败时回填用户名；密码出于安全不回填
    return render(request, 'login.html', {'error': error, 'username': username})


def logout_view(request):
    logout(request)
    return redirect('index')


def password_reset_notice(request):
    """密码重置占位页：v1.5 只提供入口，不发送邮件、不伪造重置。"""
    return render(request, 'auth/password_reset_notice.html')
