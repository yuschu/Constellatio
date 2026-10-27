"""attendance 插件路由：挂载 /plugins/attendance/。"""

from django.urls import path

from . import views

app_name = 'attendance'

urlpatterns = [
    path('', views.attendance_dashboard, name='attendance_dashboard'),
    path('check/', views.attendance_check, name='attendance_check'),
    path('records/', views.attendance_records, name='attendance_records'),
    path('rules/', views.attendance_rules, name='attendance_rules'),
    path('stats/', views.attendance_stats, name='attendance_stats'),
    path('makeup/', views.attendance_makeup, name='attendance_makeup'),
]
