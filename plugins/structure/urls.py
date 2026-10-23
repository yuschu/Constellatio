"""structure 插件路由：挂载 /plugins/structure/。"""

from django.urls import path

from . import views

app_name = 'structure'

urlpatterns = [
    path('', views.structure_overview, name='overview'),
    path('template/', views.structure_template, name='template'),   # v1.5.9 模板架构详情
    path('apply/', views.structure_apply, name='apply'),
]
