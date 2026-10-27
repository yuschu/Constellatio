"""plugin_host.workbench 守卫测试：插件停用 / 模型缺失 / 表查询失败时降级。"""

from unittest import mock

from django.apps import apps as dj_apps
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
from django.test import TestCase

from plugin_host.registry import PLUGIN_REGISTRY, plugin_counts, plugin_enabled
from plugin_host.workbench import build_dashboard
from plugins.approval.models import Approval
from plugins.user.models import Department

User = get_user_model()

ENABLED = {'approval', 'attendance', 'user', 'blockchain'}


class WorkbenchGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('wbroot', '', 'pw')
        Department.objects.create(name='研发部', is_active=True)

    def _build(self, **overrides):
        params = {
            'user': self.admin,
            'is_admin': True,
            'enabled_names': set(ENABLED),
            'range_key': 'month',
            'chart': None,
            'pending_approvals': 0,
            'attendance_today': None,
        }
        params.update(overrides)
        return build_dashboard(**params)

    def test_no_plugin_enabled_returns_degraded_structure(self):
        data = self._build(enabled_names=set())
        self.assertNotIn('approval', data['cards'])
        self.assertNotIn('attendance', data['cards'])
        self.assertIn('plugins', data['cards'])
        self.assertIsNone(data['trend'])
        self.assertIsNone(data['pie'])
        self.assertIsNone(data['dept'])

    def test_all_models_missing_returns_degraded_structure(self):
        with mock.patch('plugin_host.workbench._model', return_value=None):
            data = self._build()
        self.assertNotIn('approval', data['cards'])
        self.assertNotIn('attendance', data['cards'])
        self.assertIn('plugins', data['cards'])
        self.assertIsNone(data['dept'])

    def test_approval_model_missing_does_not_break_department_block(self):
        """回归：部门区块曾无条件使用 Approval.objects，停用 approval 时 500。"""
        real_get_model = dj_apps.get_model

        def fake_get_model(app_label, model_name):
            if (app_label, model_name) == ('approval', 'Approval'):
                return None
            return real_get_model(app_label, model_name)

        with mock.patch('plugin_host.workbench._model', side_effect=fake_get_model):
            data = self._build()
        self.assertNotIn('approval', data['cards'])
        self.assertIsNotNone(data['dept'])
        self.assertEqual(data['dept']['rows'][0]['name'], '研发部')
        self.assertEqual(data['dept']['rows'][0]['pending'], 0)

    def test_approval_disabled_skips_pending_map(self):
        data = self._build(enabled_names=ENABLED - {'approval'})
        self.assertNotIn('approval', data['cards'])
        self.assertIsNotNone(data['dept'])
        self.assertEqual(data['dept']['rows'][0]['pending'], 0)

    def test_attendance_disabled_degrades_checked_map(self):
        data = self._build(enabled_names=ENABLED - {'attendance'})
        self.assertNotIn('attendance', data['cards'])
        self.assertIsNotNone(data['dept'])
        self.assertEqual(data['dept']['rows'][0]['checked'], 0)

    def test_table_error_degrades_instead_of_raising(self):
        with mock.patch.object(Approval.objects, 'filter',
                               side_effect=OperationalError('no such table')):
            data = self._build()
        self.assertNotIn('approval', data['cards'])
        self.assertIn('plugins', data['cards'])

    def test_plugin_counts_match_registry_and_card(self):
        enabled, total = plugin_counts()
        self.assertEqual(total, len(PLUGIN_REGISTRY))
        self.assertEqual(
            enabled,
            sum(1 for key in PLUGIN_REGISTRY if plugin_enabled(key)))
        card = self._build()['cards']['plugins']
        self.assertEqual(card['total'], total)
        self.assertEqual(card['enabled'], enabled)
        self.assertEqual(card['alert'], enabled < total)
