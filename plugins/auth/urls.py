"""auth 插件路由：挂载 /plugins/auth/。"""

from django.urls import path

from . import views

app_name = 'auth'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_notice, name='password_reset_notice'),
]
