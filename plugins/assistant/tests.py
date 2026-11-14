"""A 阶段门禁：只读工具、校验层、会话落库与首页对话链路。"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from plugins.approval.models import Approval
from plugins.assistant import llm, services, tools
from plugins.assistant.models import Conversation, Message
from plugins.workspace.models import PluginSwitch

User = get_user_model()


@override_settings(
    ASSISTANT_LLM_BASE_URL='http://127.0.0.1:11434/v1',
    ASSISTANT_LLM_MODEL='qwen3:4b')
class AssistantChatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'assistant_user', password='pw', last_name='员工')
        cls.other = User.objects.create_user(
            'assistant_other', password='pw', last_name='别人')

    def setUp(self):
        self.client.force_login(self.user)

    def test_tools_are_all_read_only(self):
        """A 阶段硬断言：任何工具都不能是写操作。"""
        self.assertTrue(all(not spec['write'] for spec in tools.TOOLS.values()))
        self.assertEqual(
            {spec['schema']['function']['name'] for spec in tools.TOOLS.values()},
            set(tools.TOOLS))

    def test_approval_enum_uses_real_model_values(self):
        """文档里的旧示例是大写 + PURCHASE；落地必须以模型 choices 为准。"""
        spec = tools.TOOLS['search_approval']['schema']['function']['parameters']
        enum = spec['properties']['approval_type']['enum']
        self.assertEqual(enum, [value for value, _ in Approval.Type.choices])
        self.assertIn('expense', enum)
        self.assertNotIn('EXPENSE', enum)
        self.assertNotIn('PURCHASE', enum)

    def test_search_approval_hides_applicant_hidden_records(self):
        """助手不能把用户主动隐藏的旧单再翻出来。"""
        month = timezone.localdate().strftime('%Y-%m')
        visible = Approval.objects.create(
            approval_type=Approval.Type.LEAVE,
            title='可见单',
            applicant=self.user,
            approver=self.user,
            status=Approval.Status.APPROVED,
        )
        Approval.objects.create(
            approval_type=Approval.Type.LEAVE,
            title='已隐藏单',
            applicant=self.user,
            approver=self.user,
            status=Approval.Status.REJECTED,
            applicant_hidden=True,
        )
        result = tools.search_approval(self.user, scope='applicant', month=month)
        self.assertEqual(result['total'], 1)
        self.assertEqual([item['id'] for item in result['items']], [visible.pk])
        counts = tools.stats_approval_count(
            self.user, month=month, scope='applicant')
        self.assertEqual(counts['total'], 1)

    def test_validate_rejects_malformed_json_and_unknown_field(self):
        ok, error = services.validate_tool_call(
            {'function': {'name': 'search_approval', 'arguments': '{bad'}},
            self.user, {'search_approval'}, {'calls': {}})
        self.assertFalse(ok)
        self.assertIn('合法 JSON', error)

        ok, error = services.validate_tool_call(
            {'function': {'name': 'search_approval',
                          'arguments': json.dumps({'bogus': 1})}},
            self.user, {'search_approval'}, {'calls': {}})
        self.assertFalse(ok)
        self.assertIn('bogus', error)

    def test_validate_rejects_missing_required_argument(self):
        ok, error = services.validate_tool_call(
            {'function': {'name': 'stats_attendance', 'arguments': '{}'}},
            self.user, {'stats_attendance'}, {'calls': {}})
        self.assertFalse(ok)
        self.assertIn('month', error)

    def test_validate_denies_without_permission(self):
        ok, error = services.validate_tool_call(
            {'function': {'name': 'query_department',
                          'arguments': json.dumps({'keyword': '研发'})}},
            self.user, {'search_approval'}, {'calls': {}})
        self.assertFalse(ok)
        self.assertEqual(error, services.DENIED)

    def test_chat_post_persists_conversation_and_renders_history(self):
        reply = {'content': '本月你审批通过 1 单。'}
        with mock.patch.object(llm, 'call_llm', return_value=reply) as called:
            response = self.client.post('/', {'message': '这个月我批了几个单'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/?conversation='))
        called.assert_called_once()
        conversation = Conversation.objects.get(user=self.user)
        self.assertEqual(conversation.title, '这个月我批了几个单')
        self.assertEqual(
            list(conversation.messages.values_list('role', flat=True)),
            ['user', 'assistant'])
        self.assertEqual(
            conversation.messages.get(role=Message.Role.ASSISTANT).content,
            '本月你审批通过 1 单。')

        page = self.client.get(response['Location'])
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '这个月我批了几个单')
        self.assertContains(page, '本月你审批通过 1 单。')

    def test_chat_renders_bold_and_escapes_html(self):
        reply = {'content': '本月 **0** 单<script>alert(1)</script>'}
        with mock.patch.object(llm, 'call_llm', return_value=reply):
            response = self.client.post('/', {'message': '安全测试'})
        page = self.client.get(response['Location'])
        html = page.content.decode('utf-8')
        self.assertIn('<strong>0</strong>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_chat_post_reuses_existing_conversation(self):
        conversation = Conversation.objects.create(user=self.user, title='第一句')
        with mock.patch.object(llm, 'call_llm', return_value={'content': '收到。'}):
            response = self.client.post('/', {
                'message': '继续',
                'conversation': str(conversation.pk),
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'conversation={conversation.pk}', response['Location'])
        self.assertEqual(
            list(conversation.messages.values_list('role', flat=True)),
            ['user', 'assistant'])

    def test_chat_post_without_model_is_400_and_does_not_write(self):
        with override_settings(ASSISTANT_LLM_BASE_URL='', ASSISTANT_LLM_MODEL=''):
            response = self.client.post('/', {'message': '你好'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Conversation.objects.filter(user=self.user).exists())

    def test_chat_post_on_disabled_plugin_is_400(self):
        PluginSwitch.objects.create(app_key='assistant', enabled=False)
        response = self.client.post('/', {'message': '你好'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Conversation.objects.filter(user=self.user).exists())

    def test_other_users_cannot_read_conversation(self):
        conversation = Conversation.objects.create(user=self.user, title='私有')
        Message.objects.create(
            conversation=conversation, role=Message.Role.USER, content='机密')
        self.client.force_login(self.other)
        response = self.client.get('/?conversation=%s' % conversation.pk)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('机密', response.content.decode())

    def test_run_turn_executes_tool_and_returns_model_answer(self):
        Approval.objects.create(
            approval_type=Approval.Type.LEAVE,
            title='年假',
            applicant=self.user,
            approver=self.user,
            status=Approval.Status.APPROVED,
        )
        first = {
            'content': '',
            'tool_calls': [{
                'id': 'call_1',
                'function': {
                    'name': 'stats_approval_count',
                    'arguments': json.dumps({
                        'month': timezone.localdate().strftime('%Y-%m'),
                        'scope': 'approver',
                    }),
                },
            }],
        }
        second = {'content': '你本月审批通过 1 单。'}

        # 直接给当前用户补上审批权限，避免依赖测试库里的权限初始状态。
        perm = Permission.objects.get(codename='approval_view')
        self.user.user_permissions.add(perm)

        with mock.patch.object(llm, 'call_llm', side_effect=[first, second]):
            reply, logs = services.run_turn(
                self.user, [{'role': 'user', 'content': '这个月我批了几个单'}])
        self.assertEqual(reply, '你本月审批通过 1 单。')
        self.assertEqual(logs[0]['tool'], 'stats_approval_count')
        self.assertEqual(logs[0]['args']['scope'], 'approver')

    def test_llm_errors_become_assistant_message(self):
        with mock.patch.object(
                llm, 'call_llm', side_effect=llm.Unavailable('助手暂不可用')):
            reply = services.chat_turn(
                self.user, Conversation.objects.create(user=self.user), '你好')
        self.assertEqual(reply, '助手暂不可用')

    def test_configured_probe_reports_local_and_tool_support(self):
        with mock.patch.object(llm, 'call_llm', return_value={
                'content': '',
                'tool_calls': [{'id': 'p', 'function': {'name': 'ping',
                                                      'arguments': '{}'}}]}):
            result = llm.probe()
        self.assertTrue(result['ok'])
        self.assertTrue(result['is_local'])
        self.assertTrue(result['supports_tools'])
        self.assertGreaterEqual(result['latency_ms'], 0)

    def test_is_local_base_recognises_container_host_gateway(self):
        self.assertTrue(llm.is_local_base('http://127.0.0.1:11434/v1'))
        self.assertTrue(llm.is_local_base('http://host.docker.internal:11434/v1'))
        self.assertFalse(llm.is_local_base('https://api.openai.com/v1'))
