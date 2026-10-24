"""notify 插件路由：挂载 /plugins/notify/。"""

from django.urls import path

from . import views

app_name = 'notify'

urlpatterns = [
    path('', views.notify_list, name='notify_list'),
    path('read/<int:pk>/', views.notify_read, name='notify_read'),
    path('read-all/', views.notify_read_all, name='notify_read_all'),
]
