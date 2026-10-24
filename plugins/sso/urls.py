"""sso 插件路由：挂载 /plugins/sso/。"""

from django.urls import path

from . import views

app_name = 'sso'

urlpatterns = [
    path('login/', views.sso_login_view, name='sso_login'),
    path('', views.sso_entry, name='sso_entry'),
]
