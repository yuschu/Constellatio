"""workspace 插件视图：插件开关列表与运行时启停（v2.2.0 内置插件不外显）。"""

from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from plugin_host.permissions import require_perm
from plugin_host.registry import PLUGIN_REGISTRY
from plugin_host.signals import plugin_toggled

from .models import PluginSwitch

# 禁停清单：只留开关入口自身。v2.2.0 起真正的「系统底座」（认证 / 账号 / 组织架构 /
# 语言 / 图表引擎 / 插件页自身）用 PluginMeta.builtin 标为内置，既不进清单也不可停用；
# 这个集合只剩「理论上不该被自己停掉」的兜底。
PROTECTED = {'workspace'}


def _is_switchable(key, meta):
    """能否在界面上启停：内置插件与 PROTECTED 都不能。"""
    return key not in PROTECTED and not meta.builtin


@require_perm('workspace_manage')
def switch_list(request):
    """列出可装可停的业务插件 + 当前开关状态（DB 优先，回退静态配置）。"""
    return render(request, 'workspace/switch_list.html', switch_list_context())


def switch_list_context():
    """插件清单上下文（v2.1.0 抽出；v2.2.0 只列非内置插件）。"""
    switches = {s.app_key: s.enabled for s in PluginSwitch.objects.all()}
    rows = []
    for key, meta in PLUGIN_REGISTRY.items():
        if meta.builtin:
            continue
        rows.append({
            'key': key,
            'meta': meta,
            'enabled': switches.get(key, True),
            'protected': key in PROTECTED,
        })
    return {'rows': rows}


@require_POST
@require_perm('workspace_manage')
def switch_toggle(request, app_key):
    """切换插件开关：内置 / PROTECTED 直接回清单；写 DB → 发 plugin_toggled → 上链。"""
    meta = PLUGIN_REGISTRY.get(app_key)
    if meta is None or not _is_switchable(app_key, meta):
        return redirect('workspace:switch_list')
    enabled = request.POST.get('enabled') == '1'
    switch, _ = PluginSwitch.objects.update_or_create(
        app_key=app_key,
        defaults={'enabled': enabled, 'updated_by': request.user})
    plugin_toggled.send(
        sender=switch.__class__, app_key=app_key, enabled=enabled,
        operator_id=request.user.id)
    return redirect(_return_url(request) or 'workspace:switch_list')


def _return_url(request):
    """启停后回到哪：v2.1.0 起首页也能承载插件面板，表单带 `next` 就回那一页。"""
    next_url = request.POST.get('next') or ''
    if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return next_url
    return None
