"""workspace 插件视图：插件开关列表与运行时启停（v1.5.7 开关式 UI）。"""

from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from plugin_host.permissions import require_perm
from plugin_host.registry import PLUGIN_REGISTRY
from plugin_host.signals import plugin_toggled

from .models import PluginSwitch

# 禁停清单（v1.5.7 收敛）：只保留开关入口自身；auth / user / structure / language 均可停用。
PROTECTED = {'workspace'}

# 停用这些插件会收走关键入口：开关页显式提示，命令行 plugin_switch 可兜底恢复。
CRITICAL_WARNINGS = {
    'auth': _('停用后登录 / 登出入口关闭，已登录会话仍可用；可用 manage.py plugin_switch on auth 恢复'),
    'user': _('停用后账号、部门、角色管理入口关闭，已有会话与登录仍可用'),
    'structure': _('停用后组织架构与关系树入口关闭，组织数据不受影响'),
    # v1.6.1：图表 Provider 插件
    'charts': _('停用后考勤 / 留痕统计图表全部降级为表格，统计数据接口仍可查询；可用 manage.py plugin_switch on charts 恢复'),
}


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
            'warning': CRITICAL_WARNINGS.get(key, ''),
        })
    return render(request, 'workspace/switch_list.html', {'rows': rows})


@require_POST
@require_perm('workspace_manage')
def switch_toggle(request, app_key):
    """切换插件开关：仅拦截 workspace；写 DB → 发 plugin_toggled 信号 → 上链。"""
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
