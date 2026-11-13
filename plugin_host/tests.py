"""主题插件测试：发现 / 默认 / 契约 / 模板与静态解析。"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import get_template
from django.test import TestCase

from plugin_host.charts import discover_charts
from plugin_host.theming import discover_themes, get_theme


class ThemeDiscoveryTest(TestCase):
    def test_themes_discovered(self):
        themes = discover_themes(settings.BASE_DIR)
        self.assertEqual(set(themes), {'corporate-clean', 'risograph'})

    def test_default_theme(self):
        self.assertEqual(settings.OA_THEME, 'corporate-clean')

    def test_active_theme_dirs(self):
        """v1.5.8：两套主题的静态目录都进 STATICFILES_DIRS；v1.6 起图表 Provider 静态目录同收。"""
        themes = discover_themes(settings.BASE_DIR)
        charts = discover_charts(settings.BASE_DIR)
        static_dirs = {Path(p).resolve() for p in settings.STATICFILES_DIRS}
        expected = {t.static for t in themes.values()} | {c.static for c in charts.values()}
        self.assertEqual(static_dirs, expected)
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

    def test_hero_neutralized_for_dsh(self):
        """v2.0：DSH 统一下首页 hero 不再用彩色底板，改为中性卡片 + token。"""
        theme = get_theme(settings.BASE_DIR, 'corporate-clean')
        css = (theme.static / 'themes/corporate-clean/css/corporate-clean.css').read_text(
            encoding='utf-8')
        block = re.search(r'\.r-hero\s*\{(.*?)\}', css, re.S)
        self.assertIsNotNone(block, '缺少 .r-hero 规则')
        body = block.group(1)
        self.assertIn('var(--ds-bg-layer-1)', body)
        self.assertNotIn('linear-gradient', body)
        self.assertNotIn('#ffffff', body)

    def test_risograph_hero_keeps_original_colors(self):
        """v1.6.3：Risograph 不改 hero 配色（其首页用纸色卡片，无 r-hero 规则）。"""
        theme = get_theme(settings.BASE_DIR, 'risograph')
        css = (theme.static / 'themes/risograph/css/risograph.css').read_text(
            encoding='utf-8')
        self.assertNotIn('.r-hero', css)

    def test_shell_is_dsh_in_both_themes(self):
        """v2.0：两套主题统一 DSH 外壳，Risograph 复用同一份 CSS。"""
        for key in discover_themes(settings.BASE_DIR):
            with self.subTest(theme=key):
                base = (settings.BASE_DIR / 'themes' / key / 'templates' / 'base.html').read_text(
                    encoding='utf-8')
                self.assertIn('ds-shell', base)
                self.assertIn('ds-rail', base)
                self.assertNotIn('<footer', base)

        css = (settings.BASE_DIR / 'themes/corporate-clean/static/themes'
               '/corporate-clean/css/corporate-clean.css').read_text(encoding='utf-8')
        rail = re.search(r'\.ds-rail\s*\{(.*?)\}', css, re.S)
        self.assertIsNotNone(rail, '缺少 .ds-rail 规则')
        self.assertIn('position: sticky', rail.group(1))
        self.assertIn('--ds-rail-w: 280px', css)

        riso = (settings.BASE_DIR / 'themes/risograph/static/themes'
                '/risograph/css/risograph.css').read_text(encoding='utf-8')
        self.assertIn('themes/corporate-clean/css/corporate-clean.css', riso)

    def test_top_nav_replaced_by_rail(self):
        """v2.0：顶部横向导航由 DSH 侧栏取代；.r-nav 只保留兼容规则。"""
        for key in discover_themes(settings.BASE_DIR):
            with self.subTest(theme=key):
                base = (settings.BASE_DIR / 'themes' / key / 'templates' / 'base.html').read_text(
                    encoding='utf-8')
                self.assertNotIn('class="r-nav"', base)
                self.assertIn('ds-rail__nav', base)

        css = (settings.BASE_DIR / 'themes/corporate-clean/static/themes'
               '/corporate-clean/css/corporate-clean.css').read_text(encoding='utf-8')
        block = re.search(r'\.r-nav\s*\{(.*?)\}', css, re.S)
        self.assertIsNotNone(block, '缺少 .r-nav 兼容规则')
        self.assertIn('position: sticky', block.group(1))

    def test_dashboard_uses_active_theme_css(self):
        user = get_user_model().objects.create_user('themeuser', password='pw')
        self.client.force_login(user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'themes/corporate-clean/css/corporate-clean.css')
        self.assertContains(response, 'r-loader')

    def test_panel_element_literals_match_dsh(self):
        """v2.1.6：二级页字段 / 只读行 / 复选框按 DSH 字面量落值。

        字面量出处：dsh-web-frontend/dist/assets/index-lh_YM6sT.css 的
        `_field_181ew`（字段行）与 `_checkbox_1wz3s_1`（复选框），以及
        dsh-client-ui-settings-general/lib/client.js 的 `_WvWnq_section`
        （分区末行不画线）。同一选择器在文件里出现过多次（旧值在前、第 33 节
        在后覆盖），所以断言取**最后一次**定义，防止旧值回潮。
        """
        theme = get_theme(settings.BASE_DIR, 'corporate-clean')
        css = (theme.static / 'themes/corporate-clean/css/corporate-clean.css').read_text(
            encoding='utf-8')

        def last_body(selector):
            self.assertIn(selector, css, selector)
            return css.rsplit(selector, 1)[1].split('}', 1)[0]

        label = last_body('.ds-field__label {')
        self.assertIn('var(--ds-label-primary)', label)   # 源码 label-primary
        self.assertIn('line-height: 1.5', label)
        # 字重 500 在旧块里，第 33 节只覆盖颜色与行高，所以断言整表仍有 500
        self.assertIn('font-weight: 500', css.rsplit('.ds-field__label {', 1)[0])

        help_body = last_body('.ds-field__help {')
        self.assertIn('padding-top: 10px', help_body)     # 源码 padding:10px 0 0
        self.assertIn('var(--ds-label-secondary)', help_body)
        self.assertIn('line-height: 1.6', help_body)

        self.assertIn('line-height: 1.5', last_body('.ds-field__error {'))

        checkbox = last_body('.ds-field__checkbox {')
        self.assertIn('gap: 6px', checkbox)
        self.assertIn('line-height: 20px', checkbox)
        checkbox_input = last_body('.ds-field__checkbox input {')
        self.assertIn('width: 16px', checkbox_input)
        self.assertIn('height: 16px', checkbox_input)
        self.assertIn('accent-color: var(--ds-brand)', checkbox_input)

        self.assertIn('padding: 12px 0', last_body('.ds-settings__row {'))
        self.assertIn('.ds-fields .ds-settings__row:last-child {\n  border-bottom: none;',
                      css)


class SubpageInPlaceTest(TestCase):
    """v2.1.6：二级页改成「原地取内容」，与 DSH 点开设置一致。

    判据（可离线核对的部分）：列表里的深链带 `data-ds-panel`；`ds-shell.js` 里
    有承载面板的 host、取回后换面板、关闭还原地址三件事。真正的「不重新加载」
    由真机探针验证（marker 存活 + 地址栏往返）。
    """

    ROW_LINKS = (
        'plugins/user/templates/user/department_list.html',
        'plugins/user/templates/user/user_list.html',
        'plugins/user/templates/user/role_list.html',
        'plugins/blockchain/templates/blockchain/blockchain_list.html',
        'plugins/approval/templates/approval/approval_list.html',
        'plugins/notice/templates/notice/notice_list.html',
    )

    def test_row_links_are_flagged_for_in_place_open(self):
        for rel in self.ROW_LINKS:
            text = (settings.BASE_DIR / rel).read_text(encoding='utf-8')
            self.assertIn('data-ds-panel', text, rel)

    def test_shell_implements_in_place_panel(self):
        js = (settings.BASE_DIR / 'plugin_host/static/js/ds-shell.js').read_text(
            encoding='utf-8')
        self.assertIn("HOST_ID = 'ds-subpage-host'", js)
        self.assertIn("closest('[data-ds-panel]')", js)
        self.assertIn("'.ds-settings__panel'", js)      # 取回的就是同一块面板
        self.assertIn('document.importNode', js)
        self.assertIn('function sameUrl', js)            # 关闭时地址栏能还原
        self.assertIn("fetch(url, { method: 'POST'", js) # 面板内表单原地提交


class ThemeRuntimeSwitchTest(TestCase):
    """v1.5.8：功能区主题切换（Cookie → 模板/静态随请求切换）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('themeswitcher', password='pw')

    def test_default_theme_and_switch_entry(self):
        self.client.force_login(self.user)
        resp = self.client.get('/dashboard/')
        self.assertContains(resp, 'themes/corporate-clean/css/corporate-clean.css')
        self.assertContains(resp, 'theme/switch/')     # 功能区主题切换入口
        self.assertContains(resp, 'Risograph')          # 可选项

    def test_cookie_switches_theme(self):
        self.client.force_login(self.user)
        self.client.cookies['oa_theme'] = 'risograph'
        resp = self.client.get('/dashboard/')
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
        self.assertContains(self.client.get('/dashboard/'), 'themes/risograph/css/risograph.css')

    def test_invalid_theme_ignored_and_cookie_fallback(self):
        self.client.force_login(self.user)
        resp = self.client.post('/theme/switch/', {'theme': 'missing'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('oa_theme', resp.cookies)
        self.client.cookies['oa_theme'] = 'missing'
        self.assertContains(self.client.get('/dashboard/'), 'themes/corporate-clean/css/corporate-clean.css')

    def test_switch_requires_post_and_blocks_external_next(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/theme/switch/').status_code, 405)
        resp = self.client.post('/theme/switch/',
                                {'theme': 'risograph', 'next': 'https://evil.example/'})
        self.assertEqual(resp['Location'], '/')
