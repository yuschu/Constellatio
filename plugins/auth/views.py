"""auth 插件：统一登录 / 登出（认证后端走 Django auth，可插拔）。"""

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render


def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        error = '用户名或密码错误'

    return render(request, 'login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('index')
