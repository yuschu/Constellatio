"""v1.7.5 第二步：ExceptionGuardMiddleware 的异常分类与错误体契约。

三个开关缺一个就会「报红但不是因为页面错」，这里全部写死：
- `Client(raise_request_exception=False)`：否则视图异常被客户端重新抛出，拿不到 500 响应；
- `override_settings(DEBUG=False)`：DEBUG=True 时 server_error 会重新抛异常，测不到模板；
- 夹具 URLconf：用 `plugin_host.tests_urls_error`，不往生产 URLconf 塞测试视图。
"""

import logging
from types import SimpleNamespace
from unittest import mock

from django.test import Client, TestCase, override_settings

from plugin_host.request_id import RequestIdFilter, current_request_id, set_request_id


def _broken_urls():
    return override_settings(
        DEBUG=False, ALLOWED_HOSTS=['*'], ROOT_URLCONF='plugin_host.tests_urls_error')


class ExceptionGuardTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def test_business_error_returns_400_with_message(self):
        """BusinessError → 400，页面来自 templates/400.html，message 原样返回。"""
        with _broken_urls():
            response = self.client.get('/business/')
        self.assertEqual(response.status_code, 400)
        body = response.content.decode()
        self.assertIn('Constellatio', body)          # 品牌外壳在
        self.assertIn('400', body)
        self.assertIn('库存不足，请调整数量后重试', body)
        self.assertNotIn('Traceback', body)

    def test_object_permission_denied_returns_403(self):
        """ObjectPermissionDenied → 403，页面来自 templates/403.html，不回显 exception 文本。"""
        with _broken_urls():
            response = self.client.get('/forbidden/')
        self.assertEqual(response.status_code, 403)
        body = response.content.decode()
        self.assertIn('Constellatio', body)
        self.assertIn('403', body)
        self.assertIn('权限不足', body)
        self.assertNotIn('不能查看他人的审批单', body)   # 内部细节不外泄

    def test_stats_path_gets_json_error_body(self):
        """路径以 /stats 结尾时错误体是 {"code","message"}，且不含旧字段 error。"""
        with _broken_urls():
            response = self.client.get('/stats/')
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload['code'], 'business_error')
        self.assertEqual(payload['message'], '库存不足，请调整数量后重试')
        self.assertNotIn('error', payload)

    def test_unhandled_error_logs_stack_and_returns_500(self):
        """未处理异常 → 500 且页面无栈；同时 logger.exception 记录了 exc_info。"""
        with _broken_urls():
            with self.assertLogs('plugin_host', level='ERROR') as captured:
                response = self.client.get('/boom/')
        self.assertEqual(response.status_code, 500)
        body = response.content.decode()
        self.assertIn('Constellatio', body)
        self.assertNotIn('Traceback', body)
        self.assertNotIn('boom for test', body)
        records = [record for record in captured.records if record.exc_info]
        self.assertTrue(records, '未处理异常必须带 exc_info 记录全栈')

    def test_request_id_header_on_success_and_error(self):
        """200 与 500 都带 X-Request-Id，长度 8，且两次不同。"""
        ok = self.client.get('/plugins/auth/login/')
        self.assertEqual(ok.status_code, 200)
        with _broken_urls():
            boom = self.client.get('/boom/')
        self.assertEqual(boom.status_code, 500)
        ids = [ok.headers.get('X-Request-Id'), boom.headers.get('X-Request-Id')]
        for value in ids:
            self.assertTrue(value)
            self.assertEqual(len(value), 8)
        self.assertNotEqual(ids[0], ids[1])

    def test_guard_failure_does_not_escape(self):
        """守卫自身炸了也不能把异常抛给用户：仍返回 500 页面。"""
        with _broken_urls():
            with mock.patch(
                    'plugin_host.middleware.ExceptionGuardMiddleware._error_response',
                    side_effect=RuntimeError('guard itself broken')):
                response = self.client.get('/business/')
        self.assertEqual(response.status_code, 500)
        self.assertIn('Constellatio', response.content.decode())


class RequestIdFilterTests(TestCase):
    """filter 的取值优先级：record.request.request_id > contextvar > '-'。"""

    def _record(self):
        return logging.LogRecord('probe', logging.WARNING, __file__, 1, 'msg', None, None)

    def test_prefers_request_attribute(self):
        """4xx/5xx 日志由中间件栈返回之后才发，那时 contextvar 已 reset，必须走 request 属性。"""
        token = set_request_id('ctx-only')
        try:
            record = self._record()
            record.request = SimpleNamespace(request_id='req-attr')
            RequestIdFilter().filter(record)
        finally:
            from plugin_host.request_id import reset_request_id

            reset_request_id(token)
        self.assertEqual(record.request_id, 'req-attr')

    def test_falls_back_to_contextvar_then_dash(self):
        record = self._record()
        RequestIdFilter().filter(record)
        self.assertEqual(record.request_id, '-')      # 请求外（shell / 启动期）

        token = set_request_id('abcd1234')
        try:
            record2 = self._record()
            RequestIdFilter().filter(record2)
        finally:
            from plugin_host.request_id import reset_request_id

            reset_request_id(token)
        self.assertEqual(record2.request_id, 'abcd1234')
        self.assertEqual(current_request_id(), '-')   # reset 后不再串号
