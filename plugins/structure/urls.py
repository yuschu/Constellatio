"""structure 插件路由：挂载 /plugins/structure/。"""

from django.urls import path

from . import views

app_name = 'structure'

urlpatterns = [
    path('', views.structure_overview, name='overview'),
    path('template/', views.structure_template, name='template'),   # v1.5.9 模板架构详情
    path('apply/', views.structure_apply, name='apply'),
    path('user/<int:user_id>/', views.structure_user_detail, name='user_detail'),  # v1.5.12 用户资料
]
