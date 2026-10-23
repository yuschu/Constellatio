"""主题插件测试：发现 / 默认 / 契约 / 模板与静态解析。"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import get_template
from django.test import TestCase

from plugin_host.theming import discover_themes, get_theme


class ThemeDiscoveryTest(TestCase):
    def test_themes_discovered(self):
        themes = discover_themes(settings.BASE_DIR)
        self.assertEqual(set(themes), {'corporate-clean', 'risograph'})

    def test_default_theme(self):
        self.assertEqual(settings.OA_THEME, 'corporate-clean')

    def test_active_theme_dirs(self):
        """v1.5.8：两套主题的静态目录都进 STATICFILES_DIRS；模板由 ThemeLoader 解析。"""
        themes = discover_themes(settings.BASE_DIR)
        static_dirs = {Path(p).resolve() for p in settings.STATICFILES_DIRS}
        self.assertEqual(static_dirs, {t.static for t in themes.values()})
        origin = get_template('base.html').origin.name.replace('\\', '/')
        self.assertIn('themes/corporate-clean/templates/base.html', origin)

    def test_unknown_theme_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            get_theme(settings.BASE_DIR, 'missing')

    def test_each_theme_has_required_assets(self):
        for key, theme in discover_themes(settings.BASE_DIR).items():
            with self.subTest(theme=key):
                for name in ('base.html', 'home.html', 'login.html'):
                    self.assertTrue((theme.templates / name).is_file(), name)
                css = theme.static / 'themes' / key / 'css' / f'{key}.css'
                self.assertTrue(css.is_file(), css)

    def test_active_template_origin(self):
        origin = get_template('base.html').origin
        self.assertIn('themes/corporate-clean/templates/base.html', origin.name.replace('\\', '/'))

    def test_static_finder(self):
        self.assertIsNotNone(
            finders.find('themes/corporate-clean/css/corporate-clean.css'))

    def test_corporate_css_contract(self):
        theme = get_theme(settings.BASE_DIR, 'corporate-clean')
        css = (theme.static / 'themes/corporate-clean/css/corporate-clean.css').read_text(
            encoding='utf-8')
        for token in ('.r-btn', '.r-card', '.r-input', '.r-table', '.r-badge',
                      '.r-nav', '--r-ink', '.r-loader'):
            self.assertIn(token, css)

    def test_loader_in_base(self):
        source = get_template('base.html').template.source
        self.assertIn('r-loader', source)

    def test_home_uses_active_theme_css(self):
        user = get_user_model().objects.create_user('themeuser', password='pw')
        self.client.force_login(user)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'themes/corporate-clean/css/corporate-clean.css')
        self.assertContains(response, 'r-loader')


class ThemeRuntimeSwitchTest(TestCase):
    """v1.5.8：功能区主题切换（Cookie → 模板/静态随请求切换）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('themeswitcher', password='pw')

    def test_default_theme_and_switch_entry(self):
        self.client.force_login(self.user)
        resp = self.client.get('/')
        self.assertContains(resp, 'themes/corporate-clean/css/corporate-clean.css')
        self.assertContains(resp, 'theme/switch/')     # 功能区主题切换入口
        self.assertContains(resp, 'Risograph')          # 可选项

    def test_cookie_switches_theme(self):
        self.client.force_login(self.user)
        self.client.cookies['oa_theme'] = 'risograph'
        resp = self.client.get('/')
        self.assertContains(resp, 'themes/risograph/css/risograph.css')
        self.assertNotContains(resp, 'themes/corporate-clean/css/')

    def test_switch_view_sets_cookie_and_redirects(self):
        self.client.force_login(self.user)
        resp = self.client.post('/theme/switch/',
                                {'theme': 'risograph', 'next': '/plugins/notice/'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/plugins/notice/')
        cookie = resp.cookies['oa_theme']
        self.assertEqual(cookie.value, 'risograph')
        self.assertEqual(int(cookie['max-age']), settings.THEME_COOKIE_AGE)
        self.assertContains(self.client.get('/'), 'themes/risograph/css/risograph.css')

    def test_invalid_theme_ignored_and_cookie_fallback(self):
        self.client.force_login(self.user)
        resp = self.client.post('/theme/switch/', {'theme': 'missing'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('oa_theme', resp.cookies)
        self.client.cookies['oa_theme'] = 'missing'
        self.assertContains(self.client.get('/'), 'themes/corporate-clean/css/corporate-clean.css')

    def test_switch_requires_post_and_blocks_external_next(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/theme/switch/').status_code, 405)
        resp = self.client.post('/theme/switch/',
                                {'theme': 'risograph', 'next': 'https://evil.example/'})
        self.assertEqual(resp['Location'], '/')
