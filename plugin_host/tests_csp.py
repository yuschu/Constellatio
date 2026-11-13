"""v1.7.16：CSP 加固的可自动化验收。

覆盖 §4.1 判据：响应头（含 10 条指令 + nonce）、nonce 一致性/不复用、内联事件清零、
data-confirm 改造生效、图表页带 nonce、500 页带 CSP、admin 不豁免。
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

User = get_user_model()

HEADER = 'Content-Security-Policy'
DIRECTIVES = ('default-src', 'script-src', 'style-src', 'img-src', 'font-src',
              'connect-src', 'form-action', 'base-uri', 'frame-ancestors', 'object-src')


class CspHeaderTests(TestCase):
    """四个面都要带同一条策略。"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('csp_admin', '', 'pw')

    def _assert_policy(self, response):
        policy = response.headers.get(HEADER)
        self.assertIsNotNone(policy, f'{response.request["PATH_INFO"]} 缺 CSP 头')
        self.assertIn('nonce-', policy)
        for directive in DIRECTIVES:
            self.assertIn(directive, policy)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)   # 关键：脚本面不许放宽
        self.assertIn("object-src 'none'", policy)
        return policy

    def test_home_login_blockchain_admin_have_policy(self):
        self.client.force_login(self.admin)
        for url in ('/', '/plugins/auth/login/', '/plugins/blockchain/', '/admin/'):
            response = self.client.get(url)
            self.assertIn(response.status_code, (200, 302), url)
            policy = self._assert_policy(response) if response.status_code == 200 else None
            if policy is None:
                # 302（未登录被拦）时也必须有头：中间件在最外层
                self.assertIn('nonce-', response.headers.get(HEADER, ''))

    def test_nonce_is_consistent_within_one_response(self):
        self.client.force_login(self.admin)
        response = self.client.get('/dashboard/')
        policy = response.headers[HEADER]
        header_nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
        page_nonces = set(re.findall(r'<script nonce="([^"]+)"', response.content.decode()))
        self.assertTrue(page_nonces, '首页没有任何带 nonce 的内联脚本，断言失去意义')
        self.assertEqual(page_nonces, {header_nonce})

    def test_nonce_differs_between_requests(self):
        self.client.force_login(self.admin)
        first = re.search(r"'nonce-([^']+)'", self.client.get('/dashboard/').headers[HEADER]).group(1)
        second = re.search(r"'nonce-([^']+)'", self.client.get('/dashboard/').headers[HEADER]).group(1)
        self.assertNotEqual(first, second)

    def test_static_response_has_no_policy(self):
        """`/static/` 不发 CSP（对 JSON/JS/图片无意义）。

        测试客户端默认不服务静态文件（会 404），所以这里直接单测中间件的跳过逻辑。
        """
        from django.http import HttpResponse
        from django.test import RequestFactory

        from plugin_host.csp import CspMiddleware

        factory = RequestFactory()
        static_prefix = settings.STATIC_URL.rstrip('/')
        for path in (f'{static_prefix}/js/confirm.js',
                     f'{static_prefix}/vendor/bootstrap/bootstrap.min.css'):
            middleware = CspMiddleware(lambda request: HttpResponse('ok'))
            response = middleware(factory.get(path))
            self.assertNotIn(HEADER, response.headers, path)
        # 对照：普通页面照常发头
        middleware = CspMiddleware(lambda request: HttpResponse('ok'))
        self.assertIn(HEADER, middleware(factory.get('/')).headers)


class InlineScriptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('csp_admin2', '', 'pw')

    def test_chart_pages_have_nonce_on_scripts(self):
        """4 个图表页：页面里每个内联 script 都必须带 nonce（缺一个浏览器就会拦）。"""
        self.client.force_login(self.admin)
        for url in ('/dashboard/', '/plugins/blockchain/', '/plugins/attendance/records/',
                    '/plugins/attendance/'):
            html = self.client.get(url).content.decode()
            self.assertNotIn('<script>', html, f'{url} 仍有不带 nonce 的内联 script')
            self.assertNotIn('<script >', html, f'{url} 仍有不带 nonce 的内联 script')
            self.assertRegex(html, r'<script nonce="[^"]+">', url)

    def test_no_inline_event_attributes_in_templates(self):
        """全仓模板 `onclick=` 必须为 0（nonce 救不了内联事件）。"""
        offenders = []
        for base in ('plugins', 'plugin_host', 'templates', 'themes'):
            root = Path(settings.BASE_DIR) / base
            for path in root.rglob('*.html'):
                if 'onclick=' in path.read_text(encoding='utf-8'):
                    offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(offenders, [])

    def test_confirm_buttons_use_data_confirm(self):
        """6 个确认按钮改成 data-confirm（模板级计数，避免因测试库无数据行而漏数）。"""
        base = Path(settings.BASE_DIR)
        files = {
            'plugins/user/templates/user/department_list.html': 2,
            'plugins/user/templates/user/user_list.html': 3,
            # v2.1.3：模板页正文抽到 _template_body.html（共享给弹层与深链页），
            # 确认按钮随正文一起搬走，因此计数点跟着换到正文模板。
            'plugins/structure/templates/structure/_template_body.html': 1,
        }
        total = 0
        for rel, expected in files.items():
            text = (base / rel).read_text(encoding='utf-8')
            self.assertEqual(text.count('data-confirm="'), expected, rel)
            self.assertNotIn('onclick=', text, rel)
            total += expected
        self.assertEqual(total, 6)

        # 渲染面：结构模板页的按钮一定渲染（不依赖数据行）
        self.client.force_login(self.admin)
        html = self.client.get('/plugins/structure/template/').content.decode()
        self.assertNotIn('onclick=', html)
        self.assertIn('data-confirm=', html)

    def test_confirm_dialog_is_bound_once(self):
        """确认逻辑只能有一份实现：approval 模板曾自带绑定脚本 + 页脚日志脚本，
        若两处都在，点「通过」会弹两次确认框。这里钉住「自建绑定已并入 confirm.js」。"""
        base = Path(settings.BASE_DIR)
        for rel in ('plugins/approval/templates/approval/approval_detail.html',
                    'plugins/approval/templates/approval/approval_list.html'):
            text = (base / rel).read_text(encoding='utf-8')
            self.assertNotIn('window.confirm', text, f'{rel} 仍有自己的确认绑定')
        confirm_js = (base / 'plugin_host/static/js/confirm.js').read_text(encoding='utf-8')
        self.assertIn('data-confirm', confirm_js)
        self.assertEqual(confirm_js.count('window.confirm'), 1)

    def test_confirm_script_is_loaded_and_self_hosted(self):
        self.client.force_login(self.admin)
        html = self.client.get('/dashboard/').content.decode()
        self.assertIn('/static/js/confirm.js', html)
        self.assertNotIn('https://', html.split('<body')[0])


@override_settings(DEBUG=False)
class CspOnErrorPagesTests(TestCase):
    """异常页也要带头：403 走中间件链，硬 500 走 handler500。"""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('csp_staff', password='pw')

    def test_403_response_has_policy(self):
        self.client.force_login(self.staff)
        response = self.client.get('/plugins/structure/')     # 无 structure_view → 403
        self.assertEqual(response.status_code, 403)
        self.assertIn('nonce-', response.headers.get(HEADER, ''))

    def test_hard_500_response_has_policy(self):
        """未处理异常由 Django 默认 500 生成（在中间件链之外）→ 必须由 handler500 补头。"""
        client = Client(raise_request_exception=False)
        with override_settings(ROOT_URLCONF='plugin_host.tests_urls_error'):
            response = client.get('/boom/')
        self.assertEqual(response.status_code, 500)
        policy = response.headers.get(HEADER)
        self.assertIsNotNone(policy, '500 响应缺 CSP 头（handler500 未生效）')
        self.assertIn('nonce-', policy)
        for directive in DIRECTIVES:
            self.assertIn(directive, policy)
