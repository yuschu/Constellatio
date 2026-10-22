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
        theme = get_theme(settings.BASE_DIR, settings.OA_THEME)
        self.assertEqual(Path(settings.TEMPLATES[0]['DIRS'][0]), theme.templates)
        self.assertEqual(Path(settings.STATICFILES_DIRS[0]), theme.static)

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
