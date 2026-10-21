"""attendance 插件路由：挂载 /plugins/attendance/。"""

from django.urls import path

from . import views

app_name = 'attendance'

urlpatterns = [
    path('', views.attendance_dashboard, name='attendance_dashboard'),
    path('check/', views.attendance_check, name='attendance_check'),
]
