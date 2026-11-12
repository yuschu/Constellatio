"""v1.7.15 / 7.1：主题资源必须本地化（私有化部署断网也要有完整样式）。

两条断言各自独立：
1. 渲染出来的登录页不含任何外网资源，且引用的是本地 `vendor/bootstrap/`；
2. 两个主题的模板源码里都不再出现 CDN 域名（防只改了一个主题）。
"""

from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase

LOGIN_URL = '/plugins/auth/login/'
CDN = 'cdn.jsdelivr.net'
LOCAL_CSS = '/static/vendor/bootstrap/bootstrap.min.css'


class OfflineAssetsTests(TestCase):
    def test_login_page_references_only_local_assets(self):
        response = self.client.get(LOGIN_URL)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(CDN, html)
        self.assertNotIn('https://', html.split('<body')[0])     # head 里不该有外网引用
        self.assertIn(LOCAL_CSS, html)

    def test_vendored_bootstrap_files_exist(self):
        css = finders.find('vendor/bootstrap/bootstrap.min.css')
        js = finders.find('vendor/bootstrap/bootstrap.bundle.min.js')
        self.assertTrue(css, 'bootstrap.min.css 没进公共 static')
        self.assertTrue(js, 'bootstrap.bundle.min.js 没进公共 static')
        # 大小写死的下限：防止有人把一个空白占位文件塞进来
        self.assertGreater(Path(css).stat().st_size, 200_000)
        self.assertGreater(Path(js).stat().st_size, 60_000)

    def test_both_theme_templates_have_no_cdn(self):
        """两个主题都要改：只改一个会让切换主题后断网丢样式。"""
        base = Path(settings.BASE_DIR) / 'themes'
        offenders = []
        for path in base.glob('*/templates/*.html'):
            if CDN in path.read_text(encoding='utf-8'):
                offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(offenders, [], f'这些模板还在引用 CDN：{offenders}')
