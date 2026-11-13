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
        """v2.2.0：只剩内置默认外观（含深浅两态）；老主题 Risograph 已移除。"""
        themes = discover_themes(settings.BASE_DIR)
        self.assertEqual(set(themes), {'corporate-clean'})

    def test_default_theme(self):
        self.assertEqual(settings.OA_THEME, 'corporate-clean')

    def test_active_theme_dirs(self):
        """v1.5.8：外观目录进 STATICFILES_DIRS；v1.6 起图表 Provider 静态目录同收。"""
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

    def test_scrollbar_ported_from_dsh(self):
        """v2.2.4：滚动条照 DSH 的 scrollbar.css 移植（宽度/描边/圆角/hover/分支）。"""
        theme = get_theme(settings.BASE_DIR, 'corporate-clean')
        css = (theme.static / 'themes/corporate-clean/css/corporate-clean.css').read_text(
            encoding='utf-8')
        self.assertIn('--ds-scrollbar-width: 5px', css)
        self.assertIn('@supports not selector(::-webkit-scrollbar)', css)
        self.assertIn('scrollbar-color: var(--ds-scrollbar) transparent', css)
        thumb = re.search(r'::-webkit-scrollbar-thumb\s*\{(.*?)\}', css, re.S)
        self.assertIsNotNone(thumb, '缺少 ::-webkit-scrollbar-thumb 规则')
        body = thumb.group(1)
        self.assertIn('background: var(--ds-scrollbar)', body)
        self.assertIn('background-clip: content-box', body)
        self.assertIn('border-radius: 999px', body)
        self.assertIn('::-webkit-scrollbar-thumb:hover', css)
        self.assertIn('--ds-scrollbar-l2: #545557', css)
        self.assertIn('--ds-scrollbar-hover-l2: #65676b', css)
        self.assertRegex(
            css, r'\.ds-rail__nav\s*\{[^}]*--ds-scrollbar:\s*transparent')

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

    def test_risograph_theme_removed(self):
        """v2.2.0：老主题 Risograph 整个目录移除（外观收口成内置默认 + 深浅）。"""
        self.assertFalse((settings.BASE_DIR / 'themes' / 'risograph').exists())
        with self.assertRaises(ImproperlyConfigured):
            get_theme(settings.BASE_DIR, 'risograph')

    def test_shell_is_dsh_in_every_theme(self):
        """v2.0：所有外观统一 DSH 外壳（v2.2.0 只剩内置默认这一套）。"""
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

    def test_rail_new_session_matches_panel_rows(self):
        """v2.2.7：收起态新会话按钮与面板行同档。

        DSH SidebarRoot 的 newSession 在 wide=false 时渲染 18px（展开才是 14），
        collapsed 下还有一条与 panelRow 同值的 :hover 底色；缺任一条都会让
        新会话按钮比旁边按钮小一圈 / hover 没有反馈。
        """
        css = (settings.BASE_DIR / 'plugins/assistant/static/assistant/css/assistant.css').read_text(
            encoding='utf-8')
        self.assertIn(
            'html[data-rail-settled="true"] .as-new__ico {\n  width: 18px;\n  height: 18px;\n}', css)
        self.assertIn(
            'html[data-rail-settled="true"] .as-new:not(.is-disabled):hover {\n'
            '    background-color: var(--as-interactive-hover);\n  }', css)
        self.assertIn('html[data-rail-settled="true"] .as-panel__glyph .as-ico', css)

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

    def test_select_chevron_matches_dsh_literal(self):
        """v2.1.11：下拉去掉浏览器原生箭头，改 DSH 的 12×12 折线箭头。

        字面量出处：`dsh-client-ui-settings-models/lib/client.js` 内联的 CSS
        module（前缀 `zGbnIq_`）——DSH 设置页的 select 是**原生 `<select>` +
        纯 CSS 箭头**，没有自绘下拉组件：

            .zGbnIq_selectInput{appearance:none;
              background-image:url("data:image/svg+xml,...M3 4.5L6 7.5L9 4.5...
              stroke='%2381858C'...");
              background-position:right 12px center;
              background-repeat:no-repeat;background-size:12px 12px;
              padding-right:32px}
            select.zGbnIq_input{cursor:pointer;max-width:240px}

        #81858C 与我们浅色的 --ds-label-tertiary 同值，深色换成深色的该 token
        (#ADB2B8)；max-width:240px 是 DSH 给短标签用的，我们的下拉装部门名/
        员工姓名，照抄会截断，故不搬（第 35 节注释里记了这条偏差）。
        """
        theme = get_theme(settings.BASE_DIR, 'corporate-clean')
        css = (theme.static / 'themes/corporate-clean/css/corporate-clean.css').read_text(
            encoding='utf-8')

        block = re.search(
            r'select\.r-input:not\(\[multiple\]\),\s*select\.r-select:not\(\[multiple\]\)'
            r'\s*\{([^}]*)\}', css, re.S)
        self.assertIsNotNone(block, '缺少第 35 节的下拉规则')
        body = block.group(1)
        self.assertIn('appearance: none', body)               # 抹掉原生箭头
        self.assertIn('-webkit-appearance: none', body)       # Safari/旧内核
        self.assertIn('cursor: pointer', body)
        self.assertIn('background-position: right 12px center', body)
        self.assertIn('background-repeat: no-repeat', body)
        self.assertIn('background-size: 12px 12px', body)
        self.assertIn('padding-right: 32px', body)            # 文字不压到箭头上
        self.assertIn('M3 4.5L6 7.5L9 4.5', body)             # DSH 的 chevron 折线
        self.assertIn("stroke-width='1.5'", body)             # 源码 1.5
        self.assertIn('%2381858C', body)                      # 源码 #81858C
        self.assertNotIn('max-width', body)                   # 见 docstring 的偏差说明

        dark = re.search(
            r'html\[data-color-mode="dark"\]\s*select\.r-input:not\(\[multiple\]\),\s*'
            r'html\[data-color-mode="dark"\]\s*select\.r-select:not\(\[multiple\]\)'
            r'\s*\{([^}]*)\}', css, re.S)
        self.assertIsNotNone(dark, '缺深色下的箭头覆盖')
        self.assertIn('%23ADB2B8', dark.group(1))
        self.assertIn('M3 4.5L6 7.5L9 4.5', dark.group(1))

    def test_every_select_uses_control_class(self):
        """所有 `<select>` 都要带上 r-input/r-select，否则第 35 节的箭头落不到它身上。"""
        tags = []
        for folder in ('plugins', 'plugin_host', 'themes'):
            for path in (settings.BASE_DIR / folder).rglob('*.html'):
                text = path.read_text(encoding='utf-8')
                for tag in re.findall(r'<select[^>]*>', text):
                    tags.append((path.relative_to(settings.BASE_DIR).as_posix(), tag))
        self.assertTrue(tags, '一个 select 都没找到，选择器可能已改名')
        for name, tag in tags:
            with self.subTest(template=name, tag=tag):
                self.assertRegex(tag, r'class="[^"]*\br-(?:input|select)\b')


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
    """v1.5.8 / v2.2.0：外观收口成「内置默认（含深浅）」+ 外观包接口。

    只剩一个外观包时设置里不渲染「外观包」行；`theme/switch/` 视图保留给未来的
    外观包（放进 themes/<key>/theme.json 即被发现），但非法 key 一律忽略。
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('themeswitcher', password='pw')

    def test_default_theme_has_no_pack_switcher(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'zh-hans'
        resp = self.client.get('/dashboard/')
        self.assertContains(resp, 'themes/corporate-clean/css/corporate-clean.css')
        self.assertContains(resp, '外观')
        # 单一内置外观：不渲染外观包切换，也不再出现「主题」这一行
        self.assertNotContains(resp, '外观包')
        self.assertNotContains(resp, '两套主题共用同一份设计语言')

    def test_cookie_switch_to_removed_theme_falls_back(self):
        self.client.force_login(self.user)
        self.client.cookies['oa_theme'] = 'risograph'
        resp = self.client.get('/dashboard/')
        self.assertContains(resp, 'themes/corporate-clean/css/corporate-clean.css')

    def test_switch_view_sets_cookie_for_known_theme(self):
        self.client.force_login(self.user)
        resp = self.client.post('/theme/switch/',
                                {'theme': 'corporate-clean', 'next': '/plugins/notice/'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/plugins/notice/')
        cookie = resp.cookies['oa_theme']
        self.assertEqual(cookie.value, 'corporate-clean')
        self.assertEqual(int(cookie['max-age']), settings.THEME_COOKIE_AGE)

    def test_invalid_theme_ignored_and_cookie_fallback(self):
        self.client.force_login(self.user)
        resp = self.client.post('/theme/switch/', {'theme': 'risograph'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('oa_theme', resp.cookies)
        self.client.cookies['oa_theme'] = 'missing'
        self.assertContains(self.client.get('/dashboard/'), 'themes/corporate-clean/css/corporate-clean.css')

    def test_switch_requires_post_and_blocks_external_next(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/theme/switch/').status_code, 405)
        resp = self.client.post('/theme/switch/',
                                {'theme': 'corporate-clean', 'next': 'https://evil.example/'})
        self.assertEqual(resp['Location'], '/')


class ShortcutLayerTest(TestCase):
    """v2.2.0：快捷键层（Ctrl+/ 参考弹层 + Ctrl+Alt+数字 快速操作）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('shortcutuser', '', 'pw')

    def setUp(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'zh-hans'

    def test_reference_dialog_rendered(self):
        """参考卡挂在所有页面上：搜索行、行结构、打开器、脚本都在。"""
        resp = self.client.get('/dashboard/')
        self.assertContains(resp, 'id="ds-shortcuts"')
        self.assertContains(resp, 'data-ds-shortcuts-search')
        self.assertContains(resp, 'data-ds-shortcuts-close')
        self.assertContains(resp, 'js/shortcuts.js')
        self.assertContains(resp, 'data-ds-shortcuts-open')

    def test_quick_actions_come_from_sidebar_menus(self):
        """快速操作行由侧栏菜单生成（已按插件启停与权限过滤），按键按序号递增。"""
        resp = self.client.get('/dashboard/')
        html = resp.content.decode()
        self.assertIn('data-keys="Ctrl+Alt+1"', html)
        self.assertIn('data-shortcut-url="/dashboard/"', html)
        rows = html.count('data-ds-shortcut-row')
        self.assertGreaterEqual(rows, 3)
        self.assertLessEqual(rows, 9 + 3)   # 菜单最多 9 行 + 设置/参考/关闭 3 行

    def test_settings_row_opens_the_same_dialog(self):
        """设置面板里的「快捷键」行是一个按钮，和 Ctrl+/ 开的是同一张卡。"""
        resp = self.client.get('/dashboard/')
        self.assertContains(resp, 'ds-settings__keybtn')
        self.assertContains(resp, '快速操作与输入框操作一览')

    def test_css_literals_match_dsh_shortcuts_module(self):
        """第 36 节的字面量逐项对得上 dsh-client-ui-shortcuts 的 CSS module。"""
        css = (settings.BASE_DIR / 'themes/corporate-clean/static/themes'
               '/corporate-clean/css/corporate-clean.css').read_text(encoding='utf-8')
        block = re.search(r'\.ds-shortcuts__panel\s*\{(.*?)\}', css, re.S)
        self.assertIsNotNone(block, '缺少 .ds-shortcuts__panel 规则')
        body = block.group(1)
        self.assertIn('height: 600px', body)
        self.assertIn('max-height: calc(100dvh - 108px)', body)
        self.assertIn('border-radius: 24px', body)
        self.assertIn('translateY(30px)', body)

        search = re.search(r'\.ds-shortcuts__search\s*\{(.*?)\}', css, re.S).group(1)
        self.assertIn('flex: 0 0 60px', search)
        self.assertIn('padding: 14px 20px 10px', search)

        row = re.search(r'\.ds-shortcuts__row\s*\{(.*?)\}', css, re.S).group(1)
        self.assertIn('min-height: 42px', row)
        self.assertIn('padding: 8px', row)

        footer = re.search(r'\.ds-shortcuts__footer\s*\{(.*?)\}', css, re.S).group(1)
        self.assertIn('min-height: 52px', footer)
        self.assertIn('padding: 0 24px', footer)

        group = re.search(r'\.ds-shortcuts__group\s*\{(.*?)\}', css, re.S).group(1)
        self.assertIn('margin: 18px 8px 4px', group)

        badge = re.search(r'\.ds-shortcuts__binding\s*\{(.*?)\}', css, re.S).group(1)
        self.assertIn('height: 26px', badge)
        self.assertIn('border-radius: 10px', badge)
        self.assertIn('padding: 0 12px', badge)

    def test_key_chip_resets_bootstrap_kbd(self):
        """键帽不能继承 Bootstrap 的 kbd 底色（深底白字会把灰色药丸画成黑块）。

        这一条是实测抓到的：截图里徽标整块变黑，元素级 kbd 规则赢过了只有 font:inherit
        的 .ds-shortcuts__key。重置 padding/color/background/border 是唯一正解。
        """
        css = (settings.BASE_DIR / 'themes/corporate-clean/static/themes'
               '/corporate-clean/css/corporate-clean.css').read_text(encoding='utf-8')
        key = re.search(r'\.ds-shortcuts__key\s*\{(.*?)\}', css, re.S).group(1)
        self.assertIn('padding: 0', key)
        self.assertIn('color: inherit', key)
        self.assertIn('background: none', key)
        self.assertIn('border: 0', key)
        kbd = ''.join(re.findall(r'\.ds-kbd\s*\{(.*?)\}', css, re.S))
        self.assertIn('border: 0', kbd)
