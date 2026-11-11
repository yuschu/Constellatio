"""v1.7.4 登录守卫：框架默认拦截 + 显式白名单。

三条主线：
1. 行为：匿名访问受保护页跳登录并带 next；6 个白名单入口匿名可达；已登录不受影响。
2. 护栏（本版最有价值的断言）：用**集合相等**钉住「无守卫路由」与「匿名可达路由」，
   而不是数量相等——数量相等会在「新增一条裸奔 + 误删一条白名单」时相互抵消。
3. 配置：中间件位置（AuthenticationMiddleware 之后）与 admin 不被误伤（只做行为断言，
   不断言 Django 内部属性，避免升级假红）。
"""

import re
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.test import TestCase
from django.urls import URLPattern, get_resolver

from plugin_host.middleware import JsonAwareLoginRequiredMiddleware

User = get_user_model()

LOGIN_URL = settings.LOGIN_URL
_CONVERTER = re.compile(r'<[^>]+>')

# 静态口径：非 admin 路由里「完全没有 user_passes_test 族装饰器」的 URL 全集（7 条），
# 其中 6 条靠 @login_not_required 放行、theme/switch/ 由中间件拦截。
# 与运行时口径互补：本集合抓「新增裸奔视图」与「白名单视图被套上守卫装饰器」，
# 运行时集合抓「白名单被摘掉」与「不该放行的路由被放行」。
BARE_URLS = {
    'theme/switch/',
    'plugins/auth/login/',
    'plugins/auth/logout/',
    'plugins/auth/password-reset/',
    'plugins/language/switch/',
    'plugins/sso/login/',
    'plugins/sso/',
}

# 运行时口径：匿名必须放行的 6 条（theme/switch 不放行，它只属于登录后的外壳）。
PUBLIC_URLS = BARE_URLS - {'theme/switch/'}


def _walk(patterns, prefix=''):
    """遍历 urlpatterns，产出 (相对路由串, URLPattern)，只走非 admin。"""
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLPattern):
            if not route.startswith('admin/'):
                yield route, entry
        elif hasattr(entry, 'url_patterns'):
            yield from _walk(entry.url_patterns, route)


def _has_guard_decorator(callback):
    """是否挂了 user_passes_test 族装饰器（login_required / permission_required / require_perm）。

    user_passes_test 会给 wrapper 设 `login_url`，这是它唯一可用于静态识别的痕迹。
    """
    return hasattr(callback, 'login_url')


def _url_of(route):
    """把路由串转成可请求的 URL：把 <converter:name> 段换成假值 1。

    不用 reverse：插件路由都带 app_name 命名空间（如 auth:login），而这里拿到的是
    URLPattern.name 的裸名，reverse 会 NoReverseMatch。
    """
    return '/' + _CONVERTER.sub('1', route)


class LoginGuardBehaviorTests(TestCase):
    """匿名 / 已登录 / 越权三种身份的客户端行为。"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('guard_admin', '', 'GuardAdmin@2026')
        cls.plain = User.objects.create_user('guard_plain', password='GuardPlain@2026')

    def test_anonymous_protected_page_redirects_with_next(self):
        """匿名访问受保护页 → 302 到 LOGIN_URL，并带回原始路径的 next。"""
        response = self.client.get('/plugins/approval/')
        self.assertEqual(response.status_code, 302)
        location = urlsplit(response.headers['Location'])
        self.assertEqual(location.path, LOGIN_URL)
        # redirect_to_login 用 QueryDict.urlencode(safe="/")，斜杠不编码，所以解析 query 而不是比字面量
        self.assertEqual(parse_qs(location.query).get('next'), ['/plugins/approval/'])

    def test_anonymous_login_page_ok(self):
        """登录页本身必须匿名可达（否则中间件造成无限重定向）。"""
        self.assertEqual(self.client.get(LOGIN_URL).status_code, 200)

    def test_anonymous_language_switch_sets_cookie(self):
        """匿名 POST 语言切换：302 到目标并写语言 Cookie，不是被踢回登录页。"""
        response = self.client.post(
            '/plugins/language/switch/', {'lang': 'en', 'next': '/plugins/auth/login/'})
        self.assertEqual(response.status_code, 302)
        # 中间件拦截会变成 /plugins/auth/login/?next=...；视图放行则是精确的 next 且带 Cookie
        self.assertEqual(response.headers['Location'], '/plugins/auth/login/')
        cookie = response.cookies.get(settings.LANGUAGE_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, 'en')

    def test_anonymous_sso_entries_not_blocked(self):
        """SSO 两个入口（表单页 + 门户页）都必须匿名可达。"""
        self.assertEqual(self.client.get('/plugins/sso/').status_code, 200)
        page = self.client.get('/plugins/sso/login/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="ticket"')
        # 非法 Ticket 仍应停在表单页报错，而不是被中间件踢走
        self.assertEqual(self.client.get('/plugins/sso/login/?ticket=bad.ticket').status_code, 200)

    def test_login_round_trip_returns_to_original_page(self):
        """被拦 → 登录页带 next（含查询串）→ 登录后回原页；已登录打开登录页也回 next。"""
        target = '/plugins/approval/?x=1&y=2'
        response = self.client.get(target)
        self.assertEqual(response.status_code, 302)
        location = urlsplit(response.headers['Location'])
        self.assertEqual(parse_qs(location.query).get('next'), [target])

        page = self.client.get(location.path + '?' + location.query)
        html = page.content.decode()
        # 断言表单字段必须带 value 或按所属 action 定位：登录页上有两个 name="next"
        # （语言切换表单带 request.get_full_path，登录表单带回跳目标），
        # 只断言 'name="next"' 会两处同时命中而误通过。
        self.assertEqual(html.count('name="next"'), 2)
        expected = 'name="next" value="%s"' % target.replace('&', '&amp;')
        self.assertEqual(html.count(expected), 1)

        response = self.client.post(
            LOGIN_URL, {'username': 'guard_admin', 'password': 'GuardAdmin@2026', 'next': target})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], target)
        self.assertEqual(self.client.get(target).status_code, 200)

        # 已登录状态打开登录页 + next：也应回 next，而不是被扔回首页
        response = self.client.get(LOGIN_URL, {'next': target})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], target)

    def test_authenticated_same_page_ok(self):
        """已登录有权限 → 200；已登录无权限 → 403（v1.7.9 起；未登录仍是 302 到登录页）。"""
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/plugins/approval/').status_code, 200)

        self.client.logout()
        self.client.force_login(self.plain)
        response = self.client.get('/plugins/approval/')
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, '403', status_code=403)


class LoginGuardSetTests(TestCase):
    """两条集合护栏：静态「谁没有守卫」+ 运行时「谁匿名可达」。"""

    def test_guard_sets_are_pinned(self):
        patterns = list(_walk(get_resolver().url_patterns))
        self.assertTrue(patterns, '没有枚举到非 admin 路由，扫描本身失效了')

        unnamed = [route for route, entry in patterns if not entry.name]
        self.assertEqual(unnamed, [], '存在无名路由，运行时段会静默漏扫')

        bare = {route for route, entry in patterns if not _has_guard_decorator(entry.callback)}
        self.assertEqual(
            bare, BARE_URLS,
            '无守卫装饰器的路由集合变了：有人新增视图却忘加守卫，或给白名单视图套上了守卫装饰器')

        allowed, blocked = set(), set()
        for route, _entry in patterns:
            response = self.client.get(_url_of(route))
            location = response.headers.get('Location') or ''
            if response.status_code == 302 and LOGIN_URL in location:
                blocked.add(route)
            elif response.status_code == 401:
                # v1.7.11：匿名 + 要 JSON 的接口改为 401 JSON（不再 302），同样算「被拦」。
                # 先判类型再 .json()：某个视图若返回 401+HTML，这里要给出可读诊断，
                # 而不是抛 JSONDecodeError 把诊断信息一起吞掉。
                content_type = response.headers.get('Content-Type', '')
                self.assertIn(
                    'application/json', content_type,
                    f'{route} 返回 401 但不是 JSON（{content_type}）：{response.content[:120]!r}')
                payload = response.json()
                self.assertEqual(
                    payload.get('code'), 'authentication_required',
                    f'{route} 的 401 不是登录守卫给的：{response.content[:120]!r}')
                blocked.add(route)
            else:
                allowed.add(route)

        self.assertEqual(
            allowed, PUBLIC_URLS,
            '匿名可达集合与白名单不一致：要么漏标 @login_not_required，要么多放了不该放的路由')
        self.assertEqual(
            blocked, {route for route, _ in patterns} - PUBLIC_URLS,
            '有路由没被中间件拦下')


class LoginGuardConfigTests(TestCase):
    """配置与第三方（admin）不被误伤。"""

    def test_middleware_config_position(self):
        """v1.7.11：守卫换成内置中间件的子类（匿名 + JSON → 401），位置要求不变。"""
        middleware = list(settings.MIDDLEWARE)
        guard = 'plugin_host.middleware.JsonAwareLoginRequiredMiddleware'
        self.assertIn(guard, middleware)
        self.assertNotIn('django.contrib.auth.middleware.LoginRequiredMiddleware', middleware)
        self.assertTrue(issubclass(JsonAwareLoginRequiredMiddleware, LoginRequiredMiddleware))
        self.assertLess(
            middleware.index('django.contrib.auth.middleware.AuthenticationMiddleware'),
            middleware.index(guard))
        self.assertLess(
            middleware.index(guard),
            middleware.index('django.contrib.messages.middleware.MessageMiddleware'))
        self.assertTrue(LOGIN_URL)

    def test_admin_login_exempt_admin_index_blocked(self):
        """只做行为断言：admin 登录页可达，admin 首页仍被拦但跳 admin 自己的登录页。"""
        self.assertEqual(self.client.get('/admin/login/').status_code, 200)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(urlsplit(response.headers['Location']).path.startswith('/admin/login/'))
