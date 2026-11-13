"""对话式首页视图（v2.0.1）。

本版只交付界面与骨架：**不调用模型、不读写会话数据**。
模型服务是否可用由部署环境（ASSISTANT_LLM_BASE_URL / ASSISTANT_LLM_MODEL）
决定；未配置时页面照常打开，只禁用输入区并给出提示，绝不白屏。

v2.0.1：侧栏信息架构对齐 DSH——顶部只留 4 个单列入口（新会话/助手/看板/功能），
其余插件菜单收进「功能」抽屉。全部业务菜单平铺会让侧栏变成功能目录，
而 DSH 的极简来自「少而准」，不是配色。
"""

from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from plugin_host.context_processors import (
    COLOR_MODE_COOKIE,
    COLOR_MODES,
    DEFAULT_COLOR_MODE,
)

# 顶部固定入口对应的菜单 URL，元组顺序即侧栏渲染顺序。
# v2.0.6：加入插件入口（原插件开关页），排在「助手」之后、「看板」之前。
PRIMARY_MENU_URLS = ('/', '/plugins/workspace/', '/dashboard/')

# 「更多」菜单里的常用入口，元组顺序即菜单行顺序（DSH 的更多菜单只放轻量导航，
# 不把全部业务菜单铺进去；完整清单在业务页侧栏）。
COMMON_MENU_URLS = (
    '/plugins/attendance/',        # 考勤
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
    """对话式首页：空态 + 输入区；有会话时渲染消息流（本版无数据，分支已就位）。"""
    color_mode = _resolve_color_mode(request)
    primary_menus, common_menus = _split_menus(request)
    response = render(request, 'assistant/home_chat.html', {
        'color_mode': color_mode,
        'model_configured': _model_configured(),
        'chat_messages': [],
        'primary_menus': primary_menus,
        'common_menus': common_menus,
        'create_plugin_url': '/?prompt=' + quote(CREATE_PLUGIN_PROMPT),
        'draft_prompt': request.GET.get('prompt', ''),
    })
    if request.GET.get('mode') in COLOR_MODES:
        response.set_cookie(
            COLOR_MODE_COOKIE, color_mode,
            max_age=settings.THEME_COOKIE_AGE, samesite='Lax')
    return response


def _split_menus(request):
    """把注入的菜单拆成顶部固定入口与「更多」里常用入口两组。

    固定入口按 URL 去重后只留第一条：首页接管后「助手」与旧「工作台」都指向 /，
    两条同时出现在侧栏顶部就是两个一模一样的按钮。
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
    primary = [by_url[url] for url in PRIMARY_MENU_URLS if url in by_url]
    common = [by_url[url] for url in COMMON_MENU_URLS if url in by_url]
    return primary, common
