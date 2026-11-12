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
    # v2.0.0：首页被插件接管后，原看板仍固定可达（home_dashboard.html 一行未改）
    path('dashboard/', views.dashboard, name='dashboard'),
    path('theme/switch/', views.theme_switch, name='theme_switch'),   # v1.5.8 运行时主题切换
    # v2.0：全站深浅模式切换（首页与业务页共用同一个 Cookie）
    path('theme/mode/', views.color_mode_switch, name='color_mode_switch'),
]

# 动态挂载已启用插件的路由（/plugins/<name>/ 前缀）
for _item in settings.OA_PLUGINS:
    if _item.get('enabled'):
        _app = _item['app']
        _name = _app.rsplit('.', 1)[-1]
        urlpatterns.append(path(f'plugins/{_name}/', include(f'{_app}.urls')))

# v1.7.16：硬 500 在中间件链之外生成，默认处理器不带 CSP 头 —— 用自定义 handler500 补上
handler500 = 'plugin_host.csp.server_error'
