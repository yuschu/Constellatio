"""language 插件视图：会话级 Cookie 切换语言。"""

from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@require_POST
def language_switch(request):
    """POST lang=zh-hans|en；写会话 Cookie 后回到 next / Referer / 工作台。"""
    lang = request.POST.get('lang')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        next_url = '/'

    response = redirect(next_url)
    if lang in {code for code, _ in settings.LANGUAGES}:
        # max_age=None → 会话 Cookie，浏览器关闭后恢复默认中文
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang)
    return response
