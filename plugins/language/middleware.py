"""默认中文的语言中间件。

Django 5.2 的 LocaleMiddleware 在没有 Cookie 时会先跟随 Accept-Language，
英文浏览器首次访问会得到英文，违背"默认中文"。这里固定为：
Cookie 有效 → 用 Cookie；否则一律 LANGUAGE_CODE（zh-hans）。
"""

from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class DefaultLanguageMiddleware(LocaleMiddleware):
    """默认中文：Cookie 有效则用 Cookie，否则固定 LANGUAGE_CODE；不跟随 Accept-Language。"""

    def process_request(self, request):
        valid = {code for code, _ in settings.LANGUAGES}
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang not in valid:
            lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
