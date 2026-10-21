"""notice 插件路由：挂载 /plugins/notice/。"""

from django.urls import path

from . import views

app_name = 'notice'

urlpatterns = [
    path('', views.notice_list, name='notice_list'),
    path('new/', views.notice_create, name='notice_create'),
    path('<int:pk>/', views.notice_detail, name='notice_detail'),
]
