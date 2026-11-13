from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.attendance"

    def ready(self):
        from plugin_host.registry import PluginMeta, register
        register(PluginMeta(
            name='attendance',
            version='0.6.0',
            title=_('考勤'),
            menus=[
                # v2.0.10：考勤紧跟「看板」（order 4）——看板是业务大盘，考勤是最日常的
                # 业务入口，两者相邻；其余菜单保持注册序（缺省 order 100）。
                {'label': _('考勤'), 'icon': '▣', 'url': '/plugins/attendance/',
                 'perm': 'attendance_view', 'order': 4},
                {'label': _('签到详情'), 'icon': '☷', 'url': '/plugins/attendance/records/', 'perm': 'attendance_report_view'},
                # v1.7.2：考勤规则设置（影响全员迟到 / 早退口径）
                {'label': _('考勤规则'), 'icon': '⚙', 'url': '/plugins/attendance/rules/', 'perm': 'attendance_rule_manage'},
            ],
            permissions=[
                'attendance_view', 'attendance_check', 'attendance_report_view',
                'attendance_rule_manage',
            ],
            urls='plugins.attendance.urls',
            signals=['attendance_checked'],
            templates='attendance',
            app=self,
        ))
