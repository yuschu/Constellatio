"""AI 助手插件路由。

首页接管不依赖本模块——宿主 index 通过 PluginMeta.home_provider 调用视图；
这里保留 /plugins/assistant/ 入口，方便插件停用/启用时仍有确定的落点。
"""

from django.urls import path

from . import views

app_name = 'assistant'

urlpatterns = [
    path('', views.home, name='home'),
    path('draft/<int:message_id>/', views.approval_draft, name='approval_draft'),
    path('settings/', views.settings_page, name='settings'),
]
