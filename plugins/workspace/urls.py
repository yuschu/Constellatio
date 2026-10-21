"""workspace 插件路由：挂载 /plugins/workspace/。"""

from django.urls import path

from . import views

app_name = 'workspace'

urlpatterns = [
    path('', views.switch_list, name='switch_list'),
    path('<str:app_key>/toggle/', views.switch_toggle, name='switch_toggle'),
]
