"""v1.6：图表 Provider 发现 / 契约 / 运行时选择与降级。"""

import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from plugin_host.charts import (
    ChartRenderer,
    discover_charts,
    get_active_chart,
    get_renderer,
)
from plugin_host.registry import PLUGIN_REGISTRY


class ChartDiscoveryTests(TestCase):
    def test_echarts_provider_discovered(self):
        charts = discover_charts(settings.BASE_DIR)
        self.assertIn('echarts', charts)
        meta = charts['echarts']
        self.assertEqual(meta.name, 'ECharts')
        self.assertEqual(meta.version, '5.5.1')
        self.assertEqual(meta.renderer_path, 'charts.echarts.renderer.EChartsRenderer')

    def test_default_provider(self):
        self.assertEqual(settings.OA_CHARTS, 'echarts')
        renderer = get_active_chart()
        self.assertIsInstance(renderer, ChartRenderer)
        self.assertEqual(renderer.key, 'echarts')

    def test_static_assets_reachable(self):
        """Provider 静态目录进 STATICFILES_DIRS，collectstatic / 静态查找都能命中。"""
        static_dirs = {Path(p).resolve() for p in settings.STATICFILES_DIRS}
        meta = discover_charts(settings.BASE_DIR)['echarts']
        self.assertIn(meta.static, static_dirs)
        self.assertIsNotNone(finders.find('vendor/echarts.min.js'))
        self.assertIsNotNone(finders.find('js/echarts.js'))

    def test_renderer_asset_urls(self):
        renderer = get_renderer(discover_charts(settings.BASE_DIR)['echarts'])
        self.assertEqual(renderer.script_url, '/static/vendor/echarts.min.js')
        self.assertEqual(renderer.adapter_url, '/static/js/echarts.js')

    def test_payload_contract(self):
        renderer = get_active_chart()
        payload = renderer.payload(
            categories=['10-01', '10-02'],
            series=[{'key': 'late', 'name': 'Late', 'data': [2, 0]}],
        )
        self.assertEqual(payload['engine'], 'echarts')
        option = payload['option']
        self.assertEqual(option['xAxis']['data'], ['10-01', '10-02'])
        self.assertEqual(option['series'][0]['data'], [2, 0])
        self.assertEqual(option['series'][0]['stack'], 'attendance')
        json.dumps(payload)   # option 必须 JSON 可序列化

    def test_line_series_is_not_stacked(self):
        renderer = get_active_chart()
        option = renderer.payload(
            categories=['10-01'],
            series=[{'key': 'line', 'name': 'Line', 'data': [1], 'type': 'line'}],
        )['option']
        self.assertNotIn('stack', option['series'][0])

    def test_disabled_or_unknown_degrades(self):
        for key in ('', 'none', 'off', 'missing-provider'):
            with self.subTest(OA_CHARTS=key), override_settings(OA_CHARTS=key):
                self.assertIsNone(get_active_chart())


class ChartKindsTests(TestCase):
    """v1.6.2：payload 扩展 kind / compact / link / alert。"""

    def test_pie_payload(self):
        payload = get_active_chart().payload(
            kind='pie',
            series=[{'name': 'A', 'value': 2}, {'name': 'B', 'value': 1}],
            link='/plugins/blockchain/')
        option = payload['option']
        self.assertEqual(option['series'][0]['type'], 'pie')
        self.assertEqual(option['series'][0]['data'][1]['value'], 1)
        self.assertEqual(payload['link'], '/plugins/blockchain/')

    def test_gauge_payload_clamps_percent(self):
        payload = get_active_chart().payload(
            kind='gauge', series=[{'name': '完成率', 'value': 142}])
        series = payload['option']['series'][0]
        self.assertEqual(series['type'], 'gauge')
        self.assertEqual(series['data'][0]['value'], 100)

    def test_compact_cartesian_hides_axes(self):
        option = get_active_chart().payload(
            kind='cartesian', compact=True,
            categories=['a', 'b'],
            series=[{'name': 'x', 'data': [1, 2]}])['option']
        self.assertFalse(option['xAxis']['show'])
        self.assertNotIn('legend', option)
        self.assertEqual(option['series'][0]['data'], [1, 2])

    def test_alert_flag_is_forwarded(self):
        payload = get_active_chart().payload(
            kind='gauge', series=[{'name': '完成率', 'value': 10}], alert=True)
        self.assertTrue(payload['alert'])


class ChartManifestValidationTests(TestCase):
    def _base_with_manifest(self, data):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        provider = base / 'charts' / 'bad'
        (provider / 'static' / 'vendor').mkdir(parents=True)
        (provider / 'chart.json').write_text(json.dumps(data), encoding='utf-8')
        return base, provider

    def setUp(self):
        self.addCleanup(discover_charts.cache_clear)

    def test_missing_field_raises(self):
        base, _ = self._base_with_manifest({'name': 'Bad'})
        discover_charts.cache_clear()
        with self.assertRaises(ImproperlyConfigured):
            discover_charts(base)

    def test_missing_asset_raises(self):
        base, _ = self._base_with_manifest({
            'name': 'Bad', 'version': '1.0', 'renderer': 'plugin_host.charts.ChartRenderer',
            'static': 'static', 'asset': 'vendor/none.js',
        })
        discover_charts.cache_clear()
        with self.assertRaises(ImproperlyConfigured):
            discover_charts(base)

    def test_non_renderer_class_raises(self):
        base, provider = self._base_with_manifest({
            'name': 'Bad', 'version': '1.0', 'renderer': 'builtins.str',
            'static': 'static', 'asset': 'vendor/x.js',
        })
        (provider / 'static' / 'vendor' / 'x.js').write_text('x', encoding='utf-8')
        discover_charts.cache_clear()
        meta = discover_charts(base)['bad']
        with self.assertRaises(ImproperlyConfigured):
            get_renderer(meta)


class ChartSwitchTests(TestCase):
    """v1.6.1：图表引擎作为 Provider 插件 + workspace 运行时开关。"""

    def test_provider_registered_without_django_app(self):
        meta = PLUGIN_REGISTRY.get('charts')
        self.assertIsNotNone(meta)
        self.assertEqual(meta.menus, [])
        self.assertEqual(meta.permissions, [])
        self.assertIsNone(meta.urls)

    def test_db_switch_off_disables_provider(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='charts', enabled=False)
        self.assertIsNone(get_active_chart())

    def test_db_switch_on_keeps_provider(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='charts', enabled=True)
        self.assertEqual(get_active_chart().key, 'echarts')

    def test_env_stop_wins_over_db_on(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.create(app_key='charts', enabled=True)
        with override_settings(OA_CHARTS='none'):
            self.assertIsNone(get_active_chart())
