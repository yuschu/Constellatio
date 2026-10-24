"""workspace 兜底命令：运行时插件开关（不依赖 HTTP，停用 auth 后仍可恢复）。

用法：
    python manage.py plugin_switch list
    python manage.py plugin_switch off notice
    python manage.py plugin_switch on auth
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from plugin_host.registry import PLUGIN_REGISTRY, get_enabled_plugins
from plugin_host.signals import plugin_toggled

from ...models import PluginSwitch


def _provider_keys():
    """Provider 插件（如 charts）：不在 OA_PLUGINS，默认启用，DB 开关可覆盖。"""
    static_keys = {item['app'].rsplit('.', 1)[-1] for item in settings.OA_PLUGINS}
    return set(PLUGIN_REGISTRY) - static_keys


class Command(BaseCommand):
    help = '列出 / 切换插件运行时开关（兜底通道：停用 auth 后可用它恢复）'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs='?', default='list',
                            choices=['list', 'on', 'off'])
        parser.add_argument('app_key', nargs='?', help='插件标识，如 auth / user / language / charts')

    def handle(self, *args, **options):
        action = options['action']
        if action == 'list':
            self._list()
            return
        key = options.get('app_key')
        if not key:
            raise CommandError('需要插件标识，例如：manage.py plugin_switch off notice')
        if key not in PLUGIN_REGISTRY:
            raise CommandError(f'未注册的插件：{key}')
        switch, _ = PluginSwitch.objects.update_or_create(
            app_key=key, defaults={'enabled': action == 'on'})
        plugin_toggled.send(
            sender=PluginSwitch, app_key=key, enabled=switch.enabled, operator_id=None)
        self.stdout.write(self.style.SUCCESS(
            f'{key} -> {"启用" if switch.enabled else "停用"}'))

    def _list(self):
        enabled = {name for name, _ in get_enabled_plugins()}
        switches = {s.app_key: s.enabled for s in PluginSwitch.objects.all()}
        provider_keys = _provider_keys()
        for key, meta in PLUGIN_REGISTRY.items():
            state = switches.get(key)
            if state is None:
                state = key in enabled or key in provider_keys
            self.stdout.write(
                f'{"on " if state else "off"}  {key:12} {meta.version:8} {meta.title}')
