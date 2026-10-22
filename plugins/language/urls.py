"""language 插件路由：挂载 /plugins/language/。"""

from django.urls import path

from . import views

app_name = 'language'

urlpatterns = [
    path('switch/', views.language_switch, name='language_switch'),
]
