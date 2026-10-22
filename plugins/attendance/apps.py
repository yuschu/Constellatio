from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.attendance"

    def ready(self):
        from plugin_host.registry import register, PluginMeta
        register(PluginMeta(
            name='attendance',
            version='0.6.0',
            title=_('考勤打卡'),
            menus=[
                {'label': _('考勤打卡'), 'icon': '▣', 'url': '/plugins/attendance/', 'perm': 'attendance_view'},
                {'label': _('签到详情'), 'icon': '☷', 'url': '/plugins/attendance/records/', 'perm': 'attendance_report_view'},
            ],
            permissions=['attendance_view', 'attendance_check', 'attendance_report_view'],
            urls='plugins.attendance.urls',
            signals=['attendance_checked'],
            templates='attendance',
            app=self,
        ))
