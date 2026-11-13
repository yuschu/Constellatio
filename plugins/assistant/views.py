"""对话式首页视图（v2.0.1 → v2.1.0 主页面板）。

本版只交付界面与骨架：**不调用模型、不读写会话数据**。
模型服务是否可用由部署环境（ASSISTANT_LLM_BASE_URL / ASSISTANT_LLM_MODEL）
决定；未配置时页面照常打开，只禁用输入区并给出提示，绝不白屏。

v2.0.1：侧栏信息架构对齐 DSH——顶部只留 4 个单列入口（新会话/助手/看板/功能），
其余插件菜单收进「功能」抽屉。全部业务菜单平铺会让侧栏变成功能目录，
而 DSH 的极简来自「少而准」，不是配色。

v2.1.0：顶部三格（考勤 / 插件 / 看板）改为**在主页面板内切换**（`?panel=`），
不再跳业务页——DSH 的 panel 行只换主区内容，侧栏原地不动。业务页仍可直达，
但侧栏不再重复展示这三条入口。
"""

from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from plugin_host.context_processors import (
    COLOR_MODE_COOKIE,
    COLOR_MODES,
    DEFAULT_COLOR_MODE,
    HOME_PANEL_URLS,
)

# 顶部固定入口对应的菜单 URL，元组顺序即侧栏渲染顺序（v2.1.0 起与
# 业务页侧栏的「已由主页承载」清单同源，避免两处各写一套）。
PRIMARY_MENU_URLS = HOME_PANEL_URLS

# 菜单 URL ←→ 首页面板 key（选择器 / 高亮 / 局部刷新都按这个 key 走）
PANEL_BY_URL = {
    '/plugins/attendance/': 'attendance',
    '/plugins/workspace/': 'workspace',
    '/dashboard/': 'dashboard',
}

# 面板标题（页面 title 与 a11y 用；侧栏文案仍取菜单 label）
PANEL_TITLES = {
    'attendance': '考勤',
    'workspace': '插件',
    'dashboard': '看板',
}

# 面板可进的二级页（DSH 的详情页：crumb 返回父级 + detailTitle）。
# 只有考勤有二级页「考勤规则」；权限不足时退回上一级面板，不出 403。
PANEL_SUBS = {
    'attendance': ('rules',),
}

SUB_TITLES = {
    ('attendance', 'rules'): '考勤规则',
}

# 「更多」菜单里的常用入口，元组顺序即菜单行顺序（DSH 的更多菜单只放轻量导航，
# 不把全部业务菜单铺进去；完整清单在业务页侧栏）。考勤已在顶部固定入口，这里不重复。
COMMON_MENU_URLS = (
    '/plugins/approval/pending/',  # 待我审批
    '/plugins/approval/cc/',       # 抄送我的
    '/plugins/approval/',          # 审批中心
    '/plugins/notice/',            # 公告中心
    '/plugins/notify/',            # 消息中心
)

# DSH 的「创建你的插件」不是打开某个管理页，而是起一个带预设 prompt 的新会话
# （entry-customization/client.js 的 createPlugin → uiWorkspace.startSession）。
CREATE_PLUGIN_PROMPT = '创建一个带左侧栏入口的 Constellatio 插件。'


def _model_configured():
    """模型服务是否已配置：base_url 与 model 必须同时存在。"""
    return bool(
        getattr(settings, 'ASSISTANT_LLM_BASE_URL', '')
        and getattr(settings, 'ASSISTANT_LLM_MODEL', '')
    )


def _resolve_color_mode(request):
    """?mode= 优先，其次 Cookie，最后浅色。"""
    requested = request.GET.get('mode')
    if requested in COLOR_MODES:
        return requested
    stored = request.COOKIES.get(COLOR_MODE_COOKIE)
    if stored in COLOR_MODES:
        return stored
    return DEFAULT_COLOR_MODE


@login_required
def home(request):
    """对话式首页：空态 + 输入区；有会话时渲染消息流（本版无数据，分支已就位）。

    `?panel=attendance|workspace|dashboard` 时主区换成对应面板（同一份正文，
    与业务页共用上下文），侧栏该行高亮；不传或无权限时回对话态。
    """
    color_mode = _resolve_color_mode(request)
    panel = _resolve_panel(request)
    sub = _resolve_sub(request, panel)
    primary_menus, common_menus = _split_menus(request, panel)
    context = {
        'color_mode': color_mode,
        'model_configured': _model_configured(),
        'chat_messages': [],
        'primary_menus': primary_menus,
        'common_menus': common_menus,
        'create_plugin_url': '/?prompt=' + quote(CREATE_PLUGIN_PROMPT),
        'draft_prompt': request.GET.get('prompt', ''),
        'panel': panel,
        'panel_sub': sub,
        'panel_title': SUB_TITLES.get((panel, sub)) or PANEL_TITLES.get(panel, '助手'),
    }
    context.update(_panel_context(request, panel, sub))
    if panel != 'chat':
        theme = getattr(getattr(request, 'theme', None), 'key', settings.OA_THEME)
        # 面板正文（考勤卡 / 插件清单 / 看板）用的是主题组件类，
        # 首页平时只加载 assistant.css，切面板时才把主题表挂进来。
        context['panel_theme_css'] = f'themes/{theme}/css/{theme}.css'
    response = render(request, 'assistant/home_chat.html', context)
    if request.GET.get('mode') in COLOR_MODES:
        response.set_cookie(
            COLOR_MODE_COOKIE, color_mode,
            max_age=settings.THEME_COOKIE_AGE, samesite='Lax')
    return response


def _resolve_panel(request):
    """校验 `?panel=`：未知 key 与「当前账号点得亮、URL 却打得开」都回对话态。"""
    panel = request.GET.get('panel') or 'chat'
    if panel == 'chat' or panel not in PANEL_TITLES:
        return 'chat'
    user = request.user
    if panel == 'workspace' and not (
            user.is_superuser or user.has_perm('workspace_manage')):
        return 'chat'
    if panel == 'attendance' and not user.has_perm('attendance_check'):
        return 'chat'
    return panel


def _resolve_sub(request, panel):
    """校验 `?sub=`：只有该面板登记过的二级页才认，权限不足退回上一级。

    DSH 的详情页是同一套整页子视图（plugin detail 的 DetailTop），
    进不去时留在列表/面板本身，而不是抛 403 —— 与 `_resolve_panel` 同口径。
    """
    sub = request.GET.get('sub') or ''
    if sub not in PANEL_SUBS.get(panel, ()):
        return ''
    if (panel, sub) == ('attendance', 'rules') and not request.user.has_perm(
            'attendance_rule_manage'):
        return ''
    return sub


def _panel_context(request, panel, sub=''):
    """面板正文的上下文：直接复用业务页的构造函数，不另算一套口径。"""
    if panel == 'dashboard':
        from plugin_host.views import dashboard_context
        return dashboard_context(request)
    if panel == 'attendance':
        from plugins.attendance.views import attendance_context, rules_context
        context = attendance_context(request)
        # 面板态：入口指回面板，不走业务页；二级页要能被 home-panels.js 拦截换正文
        context['in_home_panel'] = True
        context['panel_sub'] = sub
        context['rules_entry_url'] = '/?panel=attendance&sub=rules'
        if sub == 'rules':
            context.update(rules_context(request))
            context['rules_back_url'] = '/?panel=attendance'
            context['rules_back_label'] = '考勤'
            context['rules_back_aria'] = '返回考勤'
            context['rules_next'] = '/?panel=attendance&sub=rules'
        return context
    if panel == 'workspace':
        from plugins.workspace.views import switch_list_context
        return switch_list_context()
    return {}


def _split_menus(request, panel):
    """把注入的菜单拆成顶部固定入口与「更多」里常用入口两组。

    固定入口按 URL 去重后只留第一条：首页接管后「助手」与旧「工作台」都指向 /，
    两条同时出现在侧栏顶部就是两个一模一样的按钮。

    v2.1.0：固定入口保留业务 URL（`menu.url` 不变，深链与菜单语义都还在），
    另补 `panel_key` / `panel_url` / `panel_active` 三个字段给首页侧栏用。
    """
    from plugin_host.context_processors import menus as menus_context

    all_menus = menus_context(request)['menus']
    # 同一 URL 只留第一条：首页接管后「助手」与旧「工作台」都指向 /，
    # 两条同时出现在侧栏顶部就是两个一模一样的按钮。
    by_url = {}
    for menu in all_menus:
        by_url.setdefault(menu.get('url') or '/', menu)
    # 渲染顺序以 PRIMARY_MENU_URLS 为准，菜单 order 只决定业务页侧栏；
    # 两处同源（都来自 get_menus），不另写一套顺序。
    primary = []
    for url in PRIMARY_MENU_URLS:
        menu = by_url.get(url)
        if menu is None:
            continue
        key = PANEL_BY_URL[url]
        primary.append({
            **menu,
            'panel_key': key,
            'panel_url': f'/?panel={key}',
            'panel_active': key == panel,
        })
    common = [by_url[url] for url in COMMON_MENU_URLS if url in by_url]
    return primary, common

