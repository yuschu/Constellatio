"""workspace 兜底命令：运行时插件开关（不依赖 HTTP，停用 auth 后仍可恢复）。

用法：
    python manage.py plugin_switch list
    python manage.py plugin_switch off notice
    python manage.py plugin_switch on auth
"""

from django.core.management.base import BaseCommand, CommandError

from plugin_host.registry import PLUGIN_REGISTRY, get_enabled_plugins
from plugin_host.signals import plugin_toggled

from ...models import PluginSwitch


class Command(BaseCommand):
    help = '列出 / 切换插件运行时开关（兜底通道：停用 auth 后可用它恢复）'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs='?', default='list',
                            choices=['list', 'on', 'off'])
        parser.add_argument('app_key', nargs='?', help='插件标识，如 auth / user / language')

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
        for key, meta in PLUGIN_REGISTRY.items():
            state = 'on ' if key in enabled else 'off'
            self.stdout.write(f'{state}  {key:12} {meta.version:8} {meta.title}')
