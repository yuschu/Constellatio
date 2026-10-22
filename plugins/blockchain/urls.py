"""blockchain 插件路由：挂载 /plugins/blockchain/。"""

from django.urls import path

from . import views

app_name = 'blockchain'

urlpatterns = [
    path('', views.blockchain_list, name='blockchain_list'),
    path('<int:record_id>/', views.blockchain_detail, name='record_detail'),
]
