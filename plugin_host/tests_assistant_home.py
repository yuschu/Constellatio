"""v2.0.0 对话式首页：首页接管判定 / 看板回退 / 模型未配置降级。

覆盖任务书要求的三种情形：
- 没有任何插件声明 home_provider → None；
- 声明了但插件被停用 → None；
- 声明了且插件启用 → 返回该 provider。
"""

from unittest import mock

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
        self.assertContains(response, '未配置模型服务，去配置')
        self.assertContains(response, '描述你要处理的事，/ 调用指令')
        self.assertFalse(response.context['model_configured'])
        # textarea 与发送按钮各一个 disabled
        self.assertContains(response, 'disabled', count=2)

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
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertContains(response, 'href="/dashboard/"')
        self.assertContains(response, '>看板</span>')

    def test_duplicate_home_menu_highlights_only_first(self):
        """「助手」与旧「工作台」都指向 /，只能亮一个。"""
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertEqual(response.content.decode().count('as-entry is-active'), 1)

    def test_color_mode_query_sets_cookie_and_attribute(self):
        self.client.force_login(self.user)
        response = self.client.get('/', {'mode': 'dark'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-color-mode="dark"')
        self.assertEqual(response.cookies['assistant_color_mode'].value, 'dark')

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
            'menus': [],
            'plugins_enabled': set(),
        }, request=request)
        self.assertIn('as-row--user', html)
        self.assertIn('as-row--assistant', html)
        self.assertIn('你好，有什么可以帮你？', html)
        self.assertNotIn('as-empty__title', html)
