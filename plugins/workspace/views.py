"""workspace 插件视图：插件开关列表与运行时启停。"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from plugin_host.registry import PLUGIN_REGISTRY
from plugin_host.signals import plugin_toggled

from .models import PluginSwitch

# 禁停清单：停用即锁死（auth 登录入口 / workspace 开关入口 / language 语言切换）
PROTECTED = {'auth', 'user', 'workspace', 'language'}


def require_perm(codename):
    """插件权限装饰器：未登录 → 登录页；无权限码 → 工作台。"""
    def deco(view):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(codename):
                return redirect('index')
            return view(request, *args, **kwargs)
        return wrapper
    return deco


@require_perm('workspace_manage')
def switch_list(request):
    """列出全部已注册插件 + 当前开关状态（DB 优先，回退静态配置）。"""
    switches = {s.app_key: s.enabled for s in PluginSwitch.objects.all()}
    rows = []
    for key, meta in PLUGIN_REGISTRY.items():
        rows.append({
            'key': key,
            'meta': meta,
            'enabled': switches.get(key, True),
            'protected': key in PROTECTED,
        })
    return render(request, 'workspace/switch_list.html', {'rows': rows})


@require_perm('workspace_manage')
def switch_toggle(request, app_key):
    """切换插件开关：禁停清单拦截；写 DB → 发 plugin_toggled 信号 → 上链。"""
    if app_key not in PLUGIN_REGISTRY or app_key in PROTECTED:
        return redirect('workspace:switch_list')
    enabled = request.POST.get('enabled') == '1'
    switch, _ = PluginSwitch.objects.update_or_create(
        app_key=app_key,
        defaults={'enabled': enabled, 'updated_by': request.user})
    plugin_toggled.send(
        sender=switch.__class__, app_key=app_key, enabled=enabled,
        operator_id=request.user.id)
    return redirect('workspace:switch_list')
