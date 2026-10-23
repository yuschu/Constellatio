"""language 插件视图：语言切换（持久 Cookie，插件停用后仍沿用最后设置的语言）。"""

from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@require_POST
def language_switch(request):
    """POST lang=zh-hans|en；写持久 Cookie 后回到 next / Referer / 工作台。

    v1.5.7：Cookie 持久化（LANGUAGE_COOKIE_AGE，默认 1 年）。language 插件
    停用后顶栏入口隐藏，容器级中间件继续按该 Cookie 生效=保留最后设置的语言。
    """
    lang = request.POST.get('lang')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        next_url = '/'

    response = redirect(next_url)
    if lang in {code for code, _ in settings.LANGUAGES}:
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME, lang,
            max_age=settings.LANGUAGE_COOKIE_AGE, samesite='Lax')
    return response
