"""blockchain 单元测试：链式追加 / 完整性校验 / 篡改检测。"""

import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import BlockchainRecord

User = get_user_model()


class BlockchainTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('admin', password='pw')
        # v1.5.4：留痕链接入需 blockchain_view（L2 管理岗）
        role = self.user.roles.create(name='留痕查看')
        role.permissions.add(Permission.objects.get(codename='blockchain_view'))

    def test_list_requires_perm(self):
        """无 blockchain_view 的普通用户 → 403（v1.7.9 起，原来 302 回工作台）。"""
        self.client.force_login(User.objects.create_user('staff', password='pw'))
        response = self.client.get('/plugins/blockchain/')
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, '403', status_code=403)

    def test_append_links_chain(self):
        r1 = BlockchainRecord.append(
            'approval', 'approval_finished', '1:approved', operator=self.user)
        r2 = BlockchainRecord.append('notice', 'notice_published', 'a:3')
        self.assertEqual(r1.prev_hash, '0' * 64)
        self.assertEqual(r2.prev_hash, r1.record_hash)  # 串链
        self.assertEqual(len(r2.record_hash), 64)

    def test_record_hash_algorithm(self):
        payload = 'x'
        r = BlockchainRecord.append('approval', 'approval_finished', payload)
        expect = hashlib.sha256(
            (('0' * 64) + hashlib.sha256(payload.encode()).hexdigest()).encode()).hexdigest()
        self.assertEqual(r.record_hash, expect)

    def test_verify_ok(self):
        BlockchainRecord.append('approval', 'approval_finished', '1:approved')
        BlockchainRecord.append('notice', 'notice_published', 'a:3')
        ok, broken = BlockchainRecord.verify_chain()
        self.assertTrue(ok)
        self.assertIsNone(broken)

    def test_verify_detects_tamper(self):
        BlockchainRecord.append('approval', 'approval_finished', '1:approved')
        r2 = BlockchainRecord.append('notice', 'notice_published', 'a:3')
        # 篡改第二条 payload
        BlockchainRecord.objects.filter(pk=r2.pk).update(
            payload_hash=hashlib.sha256(b'evil').hexdigest())
        ok, broken = BlockchainRecord.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(broken, r2.id)

    def test_list_links_to_record_detail(self):
        self.client.force_login(self.user)
        record = BlockchainRecord.append(
            'approval', 'approval_finished', '1:approved', operator=self.user)
        response = self.client.get('/plugins/blockchain/')
        self.assertContains(response, f'/plugins/blockchain/{record.id}/')

    def test_record_detail(self):
        self.client.force_login(self.user)
        record = BlockchainRecord.append(
            'approval', 'approval_finished', '1:approved', operator=self.user)
        response = self.client.get(f'/plugins/blockchain/{record.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, record.record_hash)
        self.assertContains(response, record.prev_hash)
        self.assertContains(response, '操作记录')

    def test_menu_label_and_page_title_are_activity_log(self):
        """v2.1.6 改名：菜单 label / 插件 title / 列表页 h2 / 详情返回按钮统一叫「活动记录」。"""
        from plugin_host.registry import get_menus

        labels = [m['label'] for m in get_menus(self.user)]
        self.assertIn('活动记录', labels)
        self.assertNotIn('留痕链', labels)

        self.client.force_login(self.user)
        response = self.client.get('/plugins/blockchain/')
        self.assertContains(response, '活动记录')
        self.assertNotContains(response, '留痕链')
        self.assertNotContains(response, '操作留痕链')

        record = BlockchainRecord.append(
            'notice', 'notice_published', 'a:2', operator=self.user)
        detail = self.client.get(f'/plugins/blockchain/{record.id}/')
        self.assertContains(detail, '返回活动记录')
        self.assertNotContains(detail, '留痕链')

    def test_activity_log_is_translated(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'en'
        response = self.client.get('/plugins/blockchain/')
        self.assertContains(response, 'Activity log')

    def test_plugin_and_action_labels_follow_language(self):
        self.client.force_login(self.user)
        record = BlockchainRecord.append(
            'notice', 'notice_published', 'a:1', operator=self.user)
        response = self.client.get(f'/plugins/blockchain/{record.id}/')
        self.assertContains(response, '公告通知')
        self.assertContains(response, '公告发布')
        self.client.cookies['django_language'] = 'en'
        response = self.client.get(f'/plugins/blockchain/{record.id}/')
        self.assertContains(response, 'Notices')
        self.assertContains(response, 'Notice published')


class BlockchainStatsTests(TestCase):
    """v1.6.1：活动统计（按日 × 来源插件）+ 权限 / 窗口 / 图表降级。"""

    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('statsviewer', password='pw')
        role = cls.viewer.roles.create(name='活动统计')
        role.permissions.add(Permission.objects.get(codename='blockchain_view'))
        now = timezone.now()

        def record(plugin, action, when, payload):
            item = BlockchainRecord.append(plugin, action, payload)
            BlockchainRecord.objects.filter(pk=item.pk).update(created_at=when)
            return item

        cls.today = timezone.localdate()
        record('user', 'user_created', now, 'user:1')
        record('user', 'user_updated', now, 'user:2')
        record('notice', 'notice_published', now, 'announcement:1')
        record('user', 'user_created', now - timedelta(days=1), 'user:3')
        record('notice', 'notice_published', now - timedelta(days=5), 'announcement:2')

    def setUp(self):
        self.client.force_login(self.viewer)

    def _get(self, **params):
        return self.client.get('/plugins/blockchain/stats/', params)

    def test_requires_blockchain_view(self):
        """v1.7.9：无权 → 403；`/stats/` 路径走 JSON 错误体。"""
        self.client.force_login(User.objects.create_user('plain', password='pw'))
        response = self._get()
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload['code'], 'permission_denied')
        self.assertEqual(payload['message'], '无权访问该功能')

    def test_default_window_aggregates_by_plugin(self):
        data = self._get().json()
        self.assertEqual(data['days'], 30)
        self.assertEqual(len(data['dates']), 30)
        self.assertEqual(data['totals']['records'], 5)
        series = {item['key']: item for item in data['series']}
        self.assertEqual(series['user']['label'], '用户与组织')
        self.assertEqual(series['notice']['label'], '公告通知')
        self.assertEqual(sum(series['user']['data']), 3)
        self.assertEqual(sum(series['notice']['data']), 2)
        # 按窗口内记录数倒序
        self.assertEqual(data['series'][0]['key'], 'user')

    def test_days_window_filters_old_records(self):
        self.assertEqual(self._get(days='2').json()['totals']['records'], 4)
        self.assertEqual(self._get(days='7').json()['totals']['records'], 5)

    def test_invalid_days_returns_400(self):
        for raw in ('0', '91', 'abc'):
            with self.subTest(days=raw):
                response = self._get(days=raw)
                self.assertEqual(response.status_code, 400)
                payload = response.json()
                # v1.7.5：JSON 错误体由 {error, message} 统一为 {code, message}
                self.assertEqual(payload['code'], 'invalid_days')
                self.assertIn('message', payload)
                self.assertNotIn('error', payload)   # 防止「兼容」回退成两套形状

    def test_payload_uses_active_chart(self):
        data = self._get(days='7').json()
        self.assertEqual(data['payload']['engine'], 'echarts')
        self.assertEqual(data['payload']['option']['xAxis']['data'], data['dates'])

    def test_payload_none_when_chart_switch_off(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='charts', enabled=False)
        data = self._get(days='7').json()
        self.assertIsNone(data['payload'])
        self.assertEqual(data['totals']['records'], 5)

    def test_list_page_renders_chart(self):
        response = self.client.get('/plugins/blockchain/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '活动统计')
        self.assertContains(response, 'blockchain-chart')
        self.assertContains(response, 'vendor/echarts.min.js')

    @override_settings(OA_CHARTS='none')
    def test_list_page_degrades_without_chart(self):
        response = self.client.get('/plugins/blockchain/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '活动统计')
        self.assertContains(response, 'blockchain-chart-fallback')
        self.assertNotContains(response, 'vendor/echarts.min.js')

