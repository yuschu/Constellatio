"""v2.0.0 对话式首页：首页接管判定 / 看板回退 / 模型未配置降级。

覆盖任务书要求的三种情形：
- 没有任何插件声明 home_provider → None；
- 声明了但插件被停用 → None；
- 声明了且插件启用 → 返回该 provider。
"""

from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings

from plugin_host.registry import PLUGIN_REGISTRY, get_home_provider
from plugins.assistant import views as assistant_views
from plugins.workspace.models import PluginSwitch

User = get_user_model()


class HomeProviderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('home_provider', password='pw')

    def test_returns_none_when_no_plugin_declares_provider(self):
        with mock.patch.dict(PLUGIN_REGISTRY, {}, clear=True):
            self.assertIsNone(get_home_provider(self.user))

    def test_returns_none_when_provider_plugin_disabled(self):
        PluginSwitch.objects.create(app_key='assistant', enabled=False)
        self.assertIsNone(get_home_provider(self.user))

    def test_returns_provider_when_plugin_enabled(self):
        self.assertIs(get_home_provider(self.user), assistant_views.home)


class AssistantHomePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'home_user', password='pw', last_name='员工')

    def test_home_renders_chat_when_model_not_configured(self):
        """首页绝不能因为模型没通就白屏：200 + 禁用输入区 + 一行提示。"""
        with override_settings(ASSISTANT_LLM_BASE_URL='', ASSISTANT_LLM_MODEL=''):
            self.client.force_login(self.user)
            response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'as-shell')
        self.assertContains(response, '未配置模型')
        self.assertContains(response, '描述你要处理的事，/ 调用指令')
        self.assertFalse(response.context['model_configured'])
        # textarea、+ 附件、发送各一个 disabled（「只读」是状态标签，不是按钮）
        self.assertContains(response, 'disabled', count=3)

    def test_rail_collapsed_state_booted_before_first_paint(self):
        """收起态要赶在首帧前落到 <html> 上。

        ds-shell.js 是 defer，最早也要等解析完才跑，冷导航时会先画 280 再跳 56；
        因此 head 里必须同步加载 rail-boot.js，且它读的是同一个会话键。
        v2.1.0：功能页侧栏不再折叠（那一格换成「返回主页」），只有首页需要它。
        """
        self.client.force_login(self.user)
        home = self.client.get('/').content.decode()
        self.assertIn('js/rail-boot.js', home)
        self.assertLess(home.index('js/rail-boot.js'), home.index('</head>'))

        dashboard = self.client.get('/dashboard/').content.decode()
        self.assertNotIn('js/rail-boot.js', dashboard)
        self.assertIn('class="ds-rail__toggle ds-rail__home"', dashboard)
        self.assertNotIn('data-ds-rail-toggle', dashboard)

        boot = Path(settings.BASE_DIR) / 'plugin_host/static/js/rail-boot.js'
        self.assertTrue(boot.exists())
        self.assertIn('constellatio.rail-collapsed', boot.read_text(encoding='utf-8'))

    @override_settings(
        ASSISTANT_LLM_BASE_URL='http://127.0.0.1:11434/v1',
        ASSISTANT_LLM_MODEL='qwen3:4b')
    def test_model_configured_enables_input(self):
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['model_configured'])
        self.assertNotContains(response, '未配置模型服务')
        self.assertNotContains(response, 'disabled')

    def test_dashboard_route_still_renders_original_board(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertContains(response, '核心数据看板')
        self.assertContains(response, '流程快捷发起')
        self.assertNotContains(response, 'as-shell')

    def test_home_falls_back_to_dashboard_when_plugin_disabled(self):
        PluginSwitch.objects.create(app_key='assistant', enabled=False)
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '核心数据看板')
        self.assertNotContains(response, 'as-shell')

    def test_dashboard_entry_comes_from_plugin_menus(self):
        """v2.1.0：看板这一格改为在首页内切换，href 指向 `/?panel=dashboard`。

        业务 URL `/dashboard/` 仍然保留为深链，只是侧栏不再直接跳过去。
        """
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertContains(response, 'href="/?panel=dashboard"')
        self.assertContains(response, 'data-home-panel="dashboard"')
        self.assertContains(response, '>看板</span>')

    def test_primary_panel_starts_with_attendance(self):
        """v2.0.7：助手入口就是侧栏顶部的「+ 新会话」，第一格改成考勤。

        助手菜单（指向 /）已下线，所以首页不再有高亮项；考勤在顶部固定入口，
        不应该在「更多」里再出现一条同名副本。
        """
        self.client.force_login(self.user)
        response = self.client.get('/')
        # 网格首项必须是考勤；「插件」入口要 workspace_manage，普通账号看不到
        self.assertEqual(
            [menu['url'] for menu in response.context['primary_menus']],
            ['/plugins/attendance/', '/dashboard/'])
        # 每一格都带一个消息内切换的落点 URL
        self.assertEqual(
            [menu['panel_url'] for menu in response.context['primary_menus']],
            ['/?panel=attendance', '/?panel=dashboard'])
        # 首页没有指向 / 的菜单了，一个面板都不亮
        self.assertEqual(response.content.decode().count('as-panel is-active'), 0)
        self.assertNotIn(
            '/plugins/attendance/',
            [menu['url'] for menu in response.context['common_menus']])

    def test_panel_query_switches_body_inside_home(self):
        """`?panel=` 只换主页正文，侧栏外壳（含收起机制）保持不动。"""
        self.client.force_login(self.user)

        for panel, marker in (
                ('dashboard', 'lc-ov-page'),
                ('attendance', 'at-page')):
            response = self.client.get('/', {'panel': panel})
            html = response.content.decode()
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-panel-body')
            self.assertContains(response, f'data-active-panel="{panel}"')
            self.assertContains(response, marker)
            self.assertContains(response, 'as-main--panel')
            self.assertContains(response, 'class="as-panel is-active"')
            # 面板态照样是首页外壳（收起脚本、账号菜单都还在）
            self.assertIn('js/rail-boot.js', html)
            self.assertNotContains(response, 'ds-rail__home')

        # 插件面板要 workspace_manage：管理员才看得到
        admin = User.objects.create_superuser('home_admin', '', 'pw')
        self.client.force_login(admin)
        response = self.client.get('/', {'panel': 'workspace'})
        self.assertContains(response, 'data-active-panel="workspace"')
        self.assertContains(response, 'ds-plugins')

        # chat 态：容器在，active=chat，正文回到对话骨架
        chat = self.client.get('/').content.decode()
        self.assertIn('data-active-panel="chat"', chat)
        self.assertIn('as-hero__title', chat)

    def test_unknown_or_forbidden_panel_falls_back_to_chat(self):
        """未知 key 与权限不足都回落对话，而不是渲染半个面板。"""
        self.client.force_login(self.user)
        response = self.client.get('/', {'panel': 'nope'})
        self.assertContains(response, 'data-active-panel="chat"')

        # 普通账号没有 workspace_manage，插件面板不该给他
        response = self.client.get('/', {'panel': 'workspace'})
        self.assertContains(response, 'data-active-panel="chat"')
        self.assertTemplateNotUsed(response, 'workspace/_panel.html')

    def test_color_mode_query_sets_cookie_and_attribute(self):
        self.client.force_login(self.user)
        response = self.client.get('/', {'mode': 'dark'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-color-mode="dark"')
        self.assertEqual(response.cookies['oa_color_mode'].value, 'dark')

        # 不带参数时沿用 Cookie，深色态可保持
        response = self.client.get('/')
        self.assertContains(response, 'data-color-mode="dark"')

    def test_message_stream_branch_renders_bubbles(self):
        """有会话时走消息流分支（本版无数据，模板骨架必须已就位）。"""
        request = RequestFactory().get('/')
        request.user = self.user
        request.csp_nonce = 'test-nonce'
        html = render_to_string('assistant/home_chat.html', {
            'color_mode': 'light',
            'model_configured': True,
            'chat_messages': [
                {'role': 'user', 'content': '你好'},
                {'role': 'assistant', 'content': '你好，有什么可以帮你？'},
            ],
            'primary_menus': [],
            'more_menus': [],
            'plugins_enabled': set(),
        }, request=request)
        self.assertIn('as-row--user', html)
        self.assertIn('as-row--assistant', html)
        self.assertIn('你好，有什么可以帮你？', html)
        self.assertNotIn('as-empty__title', html)

    def test_sidebar_caps_entries_and_hides_rest_in_drawer(self):
        """v2.0.1：顶部只留固定入口，其余插件菜单进「功能」抽屉。

        DSH 的极简来自「少而准」而不是配色——把所有插件菜单平铺在侧栏，
        信息量就是 DSH 的数倍，怎么调色都不像。
        """
        self.client.force_login(self.user)
        response = self.client.get('/')
        html = response.content.decode()
        # 「更多」抽屉存在（v2.0.10 起按 DSH PanelMoreMenu 做成按钮 + 浮层菜单），且确实承载了插件业务菜单
        self.assertIn('data-as-more-trigger', html)
        self.assertIn('id="as-more-menu"', html)
        self.assertTrue(response.context['common_menus'])
        # DSH EntryMenuContent 的两条固定行（zh 文案原文）
        self.assertIn('浏览更多插件', html)
        self.assertIn('创建你的插件', html)
        # 顶部固定入口两条（普通账号）：考勤 / 看板；「插件」入口要 workspace_manage
        self.assertEqual(len(response.context['primary_menus']), 2)

    def test_old_workbench_menu_dropped_after_home_takeover(self):
        """「工作台」与「助手」都指向 /，去重后不应再出现第二个首页入口。"""
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertNotContains(response, '工作台')
