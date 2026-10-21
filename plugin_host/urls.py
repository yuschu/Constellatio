"""URL 配置：容器路由 + 插件路由动态聚合。

插件路由由注册表按 OA_PLUGINS 配置动态 include：
启停插件 = 改配置即可，路由自动收敛。
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
]

# 动态挂载已启用插件的路由（/plugins/<name>/ 前缀）
for _item in settings.OA_PLUGINS:
    if _item.get('enabled'):
        _app = _item['app']
        _name = _app.rsplit('.', 1)[-1]
        urlpatterns.append(path(f'plugins/{_name}/', include(f'{_app}.urls')))
