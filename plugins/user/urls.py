"""user 插件路由：挂载 /plugins/user/。"""

from django.urls import path

from . import views

app_name = 'user'

urlpatterns = [
    path('departments/', views.department_list, name='department_list'),
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/status/', views.user_status, name='user_status'),
    path('roles/', views.role_list, name='role_list'),
    path('roles/new/', views.role_create, name='role_create'),
    path('roles/<int:role_id>/edit/', views.role_edit, name='role_edit'),
]
