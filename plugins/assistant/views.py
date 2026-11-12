"""对话式首页视图（v2.0.0）。

本版只交付界面与骨架：**不调用模型、不读写会话数据**。
模型服务是否可用由部署环境（ASSISTANT_LLM_BASE_URL / ASSISTANT_LLM_MODEL）
决定；未配置时页面照常打开，只禁用输入区并给出提示，绝不白屏。
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

COLOR_MODE_COOKIE = 'assistant_color_mode'
COLOR_MODES = ('light', 'dark')


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
    return 'light'


@login_required
def home(request):
    """对话式首页：空态 + 输入区；有会话时渲染消息流（本版无数据，分支已就位）。"""
    color_mode = _resolve_color_mode(request)
    response = render(request, 'assistant/home_chat.html', {
        'color_mode': color_mode,
        'model_configured': _model_configured(),
        'chat_messages': [],
    })
    if request.GET.get('mode') in COLOR_MODES:
        response.set_cookie(
            COLOR_MODE_COOKIE, color_mode,
            max_age=settings.THEME_COOKIE_AGE, samesite='Lax')
    return response
