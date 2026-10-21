"""approval 插件路由：挂载 /plugins/approval/。"""

from django.urls import path

from . import views

app_name = 'approval'

urlpatterns = [
    path('', views.approval_list, name='approval_list'),
    path('pending/', views.approval_pending, name='approval_pending'),
    path('new/', views.approval_create, name='approval_create'),
    path('<int:approval_id>/', views.approval_detail, name='approval_detail'),
]
