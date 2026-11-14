"""A 阶段门禁：只读工具、校验层、会话落库与首页对话链路。"""

import json
from datetime import date
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from plugins.approval.models import Approval
from plugins.assistant import llm, services, tools
from plugins.assistant.crypto import decrypt_secret, encrypt_secret
from plugins.assistant.eval_cases import build_cases
from plugins.assistant.eval_harness import (
    evaluate_message,
    model_tier,
    summarise,
)
from plugins.assistant.models import Conversation, LLMSettings, Message
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
        self.assertTrue(logs[0]['ok'])
        self.assertIn('result', logs[0])
        self.assertGreaterEqual(logs[0]['duration_ms'], 0)

        conversation = Conversation.objects.create(user=self.user)
        with mock.patch.object(llm, 'call_llm', side_effect=[first, second]):
            self.assertEqual(
                services.chat_turn(
                    self.user, conversation, '这个月我批了几个单'),
                '你本月审批通过 1 单。')
        stored = conversation.messages.filter(
            role=Message.Role.ASSISTANT).last()
        self.assertEqual(stored.tool_calls[0]['tool'], 'stats_approval_count')
        self.assertEqual(stored.tool_calls[0]['args']['scope'], 'approver')
        self.assertTrue(stored.tool_calls[0]['ok'])

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


def _tool_message(name, args):
    return {'tool_calls': [{'id': 'call_1', 'function': {
        'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}


class AssistantEvalTests(SimpleTestCase):
    """验收脚本本身也要有门禁：固定 20 条、评分口径、阈值与 dry-run。"""

    def setUp(self):
        self.cases = {case['id']: case for case in
                      build_cases(date(2026, 11, 14))}

    def test_eval_set_has_20_cases_and_covers_all_tools(self):
        cases = list(self.cases.values())
        self.assertEqual(len(cases), 20)
        self.assertEqual(len({case['question'] for case in cases}), 20)
        self.assertEqual({case['tool'] for case in cases}, set(tools.TOOLS))
        self.assertTrue(all(not spec['write'] for spec in tools.TOOLS.values()))

    def test_relative_month_cases_follow_injected_today(self):
        self.assertEqual(
            self.cases['A03']['expect']['month'], '2026-11')
        self.assertEqual(
            self.cases['A04']['expect']['month'], '2026-10')
        self.assertEqual(
            self.cases['A13']['expect']['month'], '2026-10')

    def test_eval_accepts_tool_default_scope_and_limit(self):
        result = evaluate_message(
            self.cases['A01'], _tool_message(
                'stats_approval_count', {'month': '2026-11'}))
        self.assertTrue(result['passed'], result['reason'])

        result = evaluate_message(
            self.cases['A14'], _tool_message('list_notice', {'limit': 20}))
        self.assertTrue(result['passed'], result['reason'])

    def test_eval_rejects_wrong_scope_and_wrong_month(self):
        result = evaluate_message(
            self.cases['A02'], _tool_message(
                'stats_approval_count',
                {'month': '2026-10', 'scope': 'approver'}))
        self.assertFalse(result['passed'])
        self.assertIn('scope', result['reason'])

        result = evaluate_message(
            self.cases['A12'], _tool_message(
                'stats_attendance', {'month': '2026-10'}))
        self.assertFalse(result['passed'])
        self.assertIn('month', result['reason'])

    def test_eval_keyword_uses_contains_not_exact_match(self):
        result = evaluate_message(
            self.cases['A17'], _tool_message(
                'query_department', {'keyword': '技术部'}))
        self.assertTrue(result['passed'], result['reason'])

        result = evaluate_message(
            self.cases['A17'], _tool_message(
                'query_department', {'keyword': '财务部'}))
        self.assertFalse(result['passed'])
        self.assertIn('技术', result['reason'])

    def test_eval_rejects_unrequested_filter_but_allows_limit(self):
        result = evaluate_message(
            self.cases['A14'], _tool_message(
                'list_notice', {'unread_only': True}))
        self.assertFalse(result['passed'])
        self.assertIn('unread_only', result['reason'])

        result = evaluate_message(
            self.cases['A18'], _tool_message(
                'query_department', {'limit': 20}))
        self.assertTrue(result['passed'], result['reason'])

    def test_eval_requires_exactly_one_tool_call(self):
        result = evaluate_message(self.cases['A01'], {'content': '0 单'})
        self.assertFalse(result['passed'])
        self.assertIn('未调用工具', result['reason'])

        message = _tool_message(
            'stats_approval_count', {'month': '2026-11'})
        message['tool_calls'].append(message['tool_calls'][0])
        result = evaluate_message(self.cases['A01'], message)
        self.assertFalse(result['passed'])
        self.assertIn('2 个工具', result['reason'])

    def test_eval_rejects_limit_outside_schema_range(self):
        result = evaluate_message(
            self.cases['A11'], _tool_message(
                'search_approval', {
                    'scope': 'approver', 'status': 'pending', 'limit': 50,
                }))
        self.assertFalse(result['passed'])
        self.assertIn('不能大于 20', result['reason'])

    def test_summary_uses_70_percent_threshold(self):
        results = [{'passed': True}] * 14 + [{'passed': False}] * 6
        summary = summarise(results, 0.70)
        self.assertEqual(summary['passed'], 14)
        self.assertTrue(summary['met'])

        results = [{'passed': True}] * 13 + [{'passed': False}] * 7
        self.assertFalse(summarise(results, 0.70)['met'])

    def test_model_tier_does_not_misread_14b_as_4b(self):
        self.assertEqual(model_tier('qwen3:4b'), '4b')
        self.assertEqual(model_tier('qwen3.5:9b'), 'other')
        self.assertEqual(model_tier('qwen3:14b'), 'other')

    def test_dry_run_prints_20_cases_without_database_or_model(self):
        output = StringIO()
        call_command('eval_assistant_a', '--dry-run', stdout=output)
        text = output.getvalue()
        self.assertIn('20 条用例结构完整', text)
        self.assertIn('A20', text)
        self.assertNotIn('结果：', text)

class _FakeResponse:
    """给 call_llm 的最小上下文管理器替身。"""

    def __init__(self, body):
        self._body = body

    def read(self):
        return json.dumps(self._body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class AssistantLLMPayloadTests(SimpleTestCase):
    """只对 Ollama 默认端口发 reasoning_effort，避免公网兼容服务不认这个字段。"""

    def _payload(self, base_url):
        config = llm.LLMConfig(
            base_url=base_url, model='qwen3:4b', timeout=5, max_tokens=128)
        body = {'choices': [{'message': {'content': 'ok'}}]}
        with mock.patch.object(
                llm.urllib.request, 'urlopen',
                return_value=_FakeResponse(body)) as opened:
            llm.call_llm([{'role': 'user', 'content': 'hi'}], config=config)
        return json.loads(opened.call_args.args[0].data.decode())

    def test_builtin_ollama_disables_thinking(self):
        payload = self._payload('http://ollama:11434/v1')
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertTrue(llm.is_ollama_base('http://127.0.0.1:11434/v1'))

    def test_public_compatible_endpoint_keeps_payload_standard(self):
        payload = self._payload('https://api.openai.com/v1')
        self.assertNotIn('reasoning_effort', payload)
        self.assertFalse(llm.is_ollama_base('http://127.0.0.1:8080/v1'))


class AssistantLLMReasoningTests(SimpleTestCase):
    """官方 Ollama 模板不认 reasoning_effort，返回前必须剥掉思考段。"""

    def test_strips_thinking_prefix_before_answer(self):
        content = '用户问的是部门人数。</think>\n\n技术部共有 2 人。'
        self.assertEqual(llm.strip_reasoning(content), '技术部共有 2 人。')

    def test_strips_complete_thinking_block(self):
        content = '<think>先查工具</think>技术部共有 2 人。'
        self.assertEqual(llm.strip_reasoning(content), '技术部共有 2 人。')

    def test_call_llm_returns_clean_content(self):
        config = llm.LLMConfig(
            base_url='http://ollama:11434/v1', model='qwen3:4b',
            timeout=5, max_tokens=128)
        body = {'choices': [{'message': {
            'content': '思考过程</think>技术部共有 2 人。'}}]}
        with mock.patch.object(
                llm.urllib.request, 'urlopen',
                return_value=_FakeResponse(body)):
            message = llm.call_llm(
                [{'role': 'user', 'content': '技术部有多少人？'}], config=config)
        self.assertEqual(message['content'], '技术部共有 2 人。')


@override_settings(SECRET_KEY='assistant-test-secret-key')
class AssistantSecretTests(SimpleTestCase):
    """API Key 字段加密：可逆、带认证、旧明文兼容。"""

    def test_roundtrip_and_ciphertext_differs_each_time(self):
        first = encrypt_secret('sk-live-secret')
        second = encrypt_secret('sk-live-secret')
        self.assertTrue(first.startswith('enc:v1:'))
        self.assertNotEqual(first, second)
        self.assertEqual(decrypt_secret(first), 'sk-live-secret')
        self.assertEqual(decrypt_secret(second), 'sk-live-secret')

    def test_tampered_ciphertext_is_rejected(self):
        token = encrypt_secret('sk-live-secret')
        self.assertEqual(decrypt_secret(token[:-2] + 'AA'), '')

    def test_legacy_plaintext_is_read_unchanged(self):
        self.assertEqual(decrypt_secret('plain-old-key'), 'plain-old-key')
        self.assertEqual(encrypt_secret(''), '')

    def test_different_secret_key_cannot_decrypt(self):
        token = encrypt_secret('sk-live-secret')
        with self.settings(SECRET_KEY='another-secret-key'):
            self.assertEqual(decrypt_secret(token), '')


@override_settings(
    ASSISTANT_LLM_BASE_URL='http://127.0.0.1:11434/v1',
    ASSISTANT_LLM_MODEL='qwen3:4b',
    ASSISTANT_LLM_API_KEY='env-secret')
class AssistantSettingsTests(TestCase):
    """配置页：权限、数据库优先、密钥不回显、测试连接不落库。"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('assistant_admin', '', 'pw')
        cls.user = User.objects.create_user('assistant_plain', password='pw')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_settings_page_requires_workspace_manage(self):
        self.client.force_login(self.user)
        response = self.client.get('/plugins/assistant/settings/')
        self.assertEqual(response.status_code, 403)

    def test_get_shows_env_fallback_without_api_key(self):
        response = self.client.get('/plugins/assistant/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'http://127.0.0.1:11434/v1')
        self.assertContains(response, 'qwen3:4b')
        self.assertContains(response, '环境变量')
        self.assertNotContains(response, 'env-secret')

    def test_save_persists_and_database_wins_over_env(self):
        response = self.client.post('/plugins/assistant/settings/', {
            'action': 'save',
            'base_url': 'http://10.0.0.8:8000/v1',
            'model': 'qwen3:8b',
            'api_key': 'db-secret',
            'timeout_seconds': '45',
            'max_tokens': '2048',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/plugins/assistant/settings/?saved=1')
        row = LLMSettings.load()
        self.assertEqual(row.base_url, 'http://10.0.0.8:8000/v1')
        self.assertEqual(row.model, 'qwen3:8b')
        self.assertTrue(row.api_key.startswith('enc:v1:'))
        self.assertNotIn('db-secret', row.api_key)
        self.assertEqual(decrypt_secret(row.api_key), 'db-secret')
        self.assertEqual(row.timeout_seconds, 45)
        self.assertEqual(row.max_tokens, 2048)
        cfg = llm.get_config()
        self.assertEqual(cfg.base_url, 'http://10.0.0.8:8000/v1')
        self.assertEqual(cfg.model, 'qwen3:8b')
        self.assertEqual(cfg.api_key, 'db-secret')
        self.assertEqual(cfg.timeout, 45.0)

    def test_blank_api_key_keeps_existing_and_clear_removes_it(self):
        LLMSettings.objects.create(
            pk=1, base_url='http://127.0.0.1:11434/v1',
            model='qwen3:4b', api_key='old-secret')
        response = self.client.post('/plugins/assistant/settings/', {
            'action': 'save',
            'base_url': 'http://127.0.0.1:11434/v1',
            'model': 'qwen3:4b',
            'api_key': '',
            'timeout_seconds': '30',
            'max_tokens': '1024',
        })
        self.assertEqual(response.status_code, 302)
        row = LLMSettings.load()
        self.assertTrue(row.api_key.startswith('enc:v1:'))
        self.assertEqual(decrypt_secret(row.api_key), 'old-secret')

        response = self.client.post('/plugins/assistant/settings/', {
            'action': 'save',
            'base_url': 'http://127.0.0.1:11434/v1',
            'model': 'qwen3:4b',
            'clear_api_key': 'on',
            'timeout_seconds': '30',
            'max_tokens': '1024',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LLMSettings.load().api_key, '')

    def test_test_connection_does_not_save(self):
        with mock.patch(
                'plugins.assistant.views.llm.probe',
                return_value={
                    'ok': True, 'latency_ms': 321, 'is_local': True,
                    'supports_tools': True, 'model': 'qwen3:4b',
                }) as probe:
            response = self.client.post('/plugins/assistant/settings/', {
                'action': 'test',
                'base_url': 'http://127.0.0.1:11434/v1',
                'model': 'qwen3:4b',
                'api_key': '',
                'timeout_seconds': '30',
                'max_tokens': '1024',
            })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LLMSettings.objects.exists())
        self.assertContains(response, '连接成功')
        self.assertContains(response, '321 ms')
        probe.assert_called_once()
        cfg = probe.call_args.args[0]
        self.assertEqual(cfg.base_url, 'http://127.0.0.1:11434/v1')
        self.assertEqual(cfg.model, 'qwen3:4b')
        self.assertEqual(cfg.api_key, 'env-secret')

    def test_public_address_shows_data_flow_warning(self):
        LLMSettings.objects.create(
            pk=1, base_url='https://llm.example.com/v1', model='qwen3:4b')
        response = self.client.get('/plugins/assistant/settings/')
        self.assertContains(response, '公网地址')
        self.assertContains(response, '发送到该地址')

    def test_blank_pair_save_clears_database_and_falls_back_to_env(self):
        LLMSettings.objects.create(
            pk=1, base_url='http://10.0.0.8:8000/v1',
            model='qwen3:8b', api_key='db-secret')
        response = self.client.post('/plugins/assistant/settings/', {
            'action': 'save',
            'base_url': '',
            'model': '',
            'timeout_seconds': '30',
            'max_tokens': '1024',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/plugins/assistant/settings/?reset=1')
        self.assertFalse(LLMSettings.objects.exists())
        cfg = llm.get_config()
        self.assertEqual(cfg.base_url, 'http://127.0.0.1:11434/v1')
        self.assertEqual(cfg.model, 'qwen3:4b')
        self.assertEqual(cfg.api_key, 'env-secret')

    def test_settings_page_renders_english_copy(self):
        self.client.cookies['django_language'] = 'en'
        response = self.client.get('/plugins/assistant/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assistant model settings')
        self.assertContains(response, 'Endpoint URL')
        self.assertNotContains(response, '助手模型配置')

    def test_legacy_plaintext_row_is_read_until_next_save(self):
        LLMSettings.objects.create(
            pk=1, base_url='http://127.0.0.1:11434/v1',
            model='qwen3:4b', api_key='')
        LLMSettings.objects.filter(pk=1).update(api_key='legacy-secret')
        cfg = llm.get_config()
        self.assertEqual(cfg.api_key, 'legacy-secret')

    def test_half_config_is_rejected(self):
        response = self.client.post('/plugins/assistant/settings/', {
            'action': 'save',
            'base_url': 'http://127.0.0.1:11434/v1',
            'model': '',
            'timeout_seconds': '30',
            'max_tokens': '1024',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '填了接口地址就必须填模型名')
        self.assertFalse(LLMSettings.objects.exists())
