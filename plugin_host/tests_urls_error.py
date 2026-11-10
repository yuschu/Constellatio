"""测试夹具：只包含「会抛异常」的视图，供 500 / 异常分类用例通过
`override_settings(ROOT_URLCONF='plugin_host.tests_urls_error')` 挂载。

不往生产 URLconf 塞任何测试视图——这条模块只在测试运行时被引用。
末尾把真实 URLconf 一起挂进来：错误模板（继承 base.html）里用了
`{% url 'index' %}` / `{% url 'language:language_switch' %}` / `{% url 'theme_switch' %}`，
如果夹具不提供这些名字，404 页渲染会抛 NoReverseMatch 变成 500，把用例带偏。
"""

from django.contrib.auth.decorators import login_not_required
from django.urls import include, path


@login_not_required          # 夹具视图只测错误处理，不该被登录守卫拦成 302
def boom(request):
    """未处理异常 → 500。"""
    raise RuntimeError('boom for test')


@login_not_required
def business(request):
    """业务校验失败 → 400（Step 3.3 的 BusinessError）。"""
    from plugin_host.exceptions import BusinessError

    raise BusinessError('库存不足，请调整数量后重试')


@login_not_required
def forbidden(request):
    """对象级越权 → 403（Step 3.3 的 ObjectPermissionDenied）。"""
    from plugin_host.exceptions import ObjectPermissionDenied

    raise ObjectPermissionDenied('不能查看他人的审批单')


urlpatterns = [
    path('boom/', boom, name='test_boom'),
    path('business/', business, name='test_business'),
    path('forbidden/', forbidden, name='test_forbidden'),
    # 路径以 /stats 结尾 → ExceptionGuardMiddleware 走 JSON 错误体分支
    path('stats/', business, name='test_business_stats'),
    # 真实路由放最后：保住 index / theme_switch / language:* 等名字，错误页才能正常渲染
    path('', include('plugin_host.urls')),
]
