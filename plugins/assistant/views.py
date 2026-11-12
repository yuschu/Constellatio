"""对话式首页视图（v2.0.1）。

本版只交付界面与骨架：**不调用模型、不读写会话数据**。
模型服务是否可用由部署环境（ASSISTANT_LLM_BASE_URL / ASSISTANT_LLM_MODEL）
决定；未配置时页面照常打开，只禁用输入区并给出提示，绝不白屏。

v2.0.1：侧栏信息架构对齐 DSH——顶部只留 4 个单列入口（新会话/助手/看板/功能），
其余插件菜单收进「功能」抽屉。全部业务菜单平铺会让侧栏变成功能目录，
而 DSH 的极简来自「少而准」，不是配色。
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from plugin_host.context_processors import (
    COLOR_MODE_COOKIE,
    COLOR_MODES,
    DEFAULT_COLOR_MODE,
)

# 顶部固定入口对应的菜单 URL。其余菜单一律进「功能」抽屉。
PRIMARY_MENU_URLS = ('/', '/dashboard/')


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
    primary_menus, more_menus = _split_menus(request)
    response = render(request, 'assistant/home_chat.html', {
        'color_mode': color_mode,
        'model_configured': _model_configured(),
        'chat_messages': [],
        'primary_menus': primary_menus,
        'more_menus': more_menus,
    })
    if request.GET.get('mode') in COLOR_MODES:
        response.set_cookie(
            COLOR_MODE_COOKIE, color_mode,
            max_age=settings.THEME_COOKIE_AGE, samesite='Lax')
    return response


def _split_menus(request):
    """把注入的菜单拆成顶部固定入口与「功能」抽屉两组。

    固定入口按 URL 去重后只留第一条：首页接管后「助手」与旧「工作台」都指向 /，
    两条同时出现在侧栏顶部就是两个一模一样的按钮。
    """
    from plugin_host.context_processors import menus as menus_context

    all_menus = menus_context(request)['menus']
    seen = set()
    primary = []
    for menu in all_menus:
        url = menu.get('url') or '/'
        if url in PRIMARY_MENU_URLS and url not in seen:
            primary.append(menu)
            seen.add(url)
    more = [m for m in all_menus if (m.get('url') or '/') not in PRIMARY_MENU_URLS]
    return primary, more
