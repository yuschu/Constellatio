"""v1.7.5 第一步：错误页模板（400/403/404/500）渲染与安全。

这些用例只验证「模板本身」：品牌外壳、错误码、返回按钮、不泄漏栈；
业务异常 → 400/403 的映射由第二步的 ExceptionGuardMiddleware 引入后再补。
"""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.utils import translation
from django.views import defaults


class ErrorPageRenderTests(TestCase):
    """DEBUG=False 时 Django 默认 handler 会自动渲染容器根 templates/ 下的四个模板。"""

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['*'])
    def test_404_renders_branded_page(self):
        """不存在的路径 → 404 品牌页（错误码 + 说明 + 返回工作台），不是 Django 默认页。"""
        response = self.client.get('/no-such-page-for-test/')
        self.assertEqual(response.status_code, 404)
        body = response.content.decode()
        self.assertIn('Constellatio', body)
        self.assertIn('404', body)
        self.assertIn('返回工作台', body)
        self.assertNotIn('Using the URLconf defined in', body)

    def test_500_renders_branded_page_without_stack(self):
        """server_error 用空上下文渲染 500 模板：不能报错、不能出现栈信息。"""
        response = defaults.server_error(self.factory.get('/boom/'))
        self.assertEqual(response.status_code, 500)
        body = response.content.decode()
        self.assertIn('Constellatio', body)
        self.assertIn('500', body)
        self.assertIn('返回工作台', body)
        for leak in ('Traceback', 'RuntimeError', 'django/', 'File "'):
            self.assertNotIn(leak, body)

    def test_403_and_400_render_branded_pages(self):
        """403 / 400 也走容器模板（403 会带上 exception 上下文，但不渲染其内容）。"""
        # RequestFactory 不经过中间件，这里补上 AuthenticationMiddleware 会设置的 request.user，
        # 否则 base.html 的上下文处理器会因缺 user 报错（真实请求链路上不存在这个问题）。
        forbidden_request = self.factory.get('/forbidden/')
        forbidden_request.user = AnonymousUser()
        forbidden = defaults.permission_denied(
            forbidden_request, PermissionError('内部细节不应出现'))
        self.assertEqual(forbidden.status_code, 403)
        body = forbidden.content.decode()
        self.assertIn('403', body)
        self.assertIn('权限不足', body)
        self.assertNotIn('内部细节不应出现', body)

        bad_request = self.factory.get('/bad/')
        bad_request.user = AnonymousUser()
        bad = defaults.bad_request(bad_request, None)
        self.assertEqual(bad.status_code, 400)
        self.assertIn('400', bad.content.decode())

    def test_error_pages_are_translated(self):
        """新增文案必须进 en 目录（.po → compile_mo.py），否则英文界面回退中文。"""
        with translation.override('en'):
            body = defaults.server_error(self.factory.get('/boom/')).content.decode()
        self.assertIn('Server error', body)
        self.assertIn('Back to workspace', body)
