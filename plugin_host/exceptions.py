"""容器级业务异常（v1.7.5）。

两个类的边界（与 LoginRequiredMiddleware / require_perm 不重叠）：
- `BusinessError`：用户可理解的业务校验失败 → 400，message **原样**返回。
  注意 message 可能含用户输入，渲染到页面时必须走模板默认转义，禁止 `|safe`。
- `ObjectPermissionDenied`：对象级越权 → 403。
  继承 Django `PermissionDenied`：即使某条路径没走到 `ExceptionGuardMiddleware`
  （例如在模板渲染、惰性求值时抛出），Django 也会用 `templates/403.html` 兜底。
"""

from django.core.exceptions import PermissionDenied


class BusinessError(Exception):
    """业务校验失败：统一 400，code 用于接口区分，message 直接给用户看。"""

    status_code = 400
    code = 'business_error'

    def __init__(self, message='', code=None):
        super().__init__(message)
        if code:
            self.code = code

    @property
    def message(self):
        return str(self) or '请求无法处理'


class ObjectPermissionDenied(PermissionDenied):
    """对象级越权：统一 403（与 require_perm 的「302 回工作台」是两种语义，不要混）。"""

    status_code = 403
    code = 'permission_denied'

    def __init__(self, message=''):
        super().__init__(message)

    @property
    def message(self):
        return str(self) or '无权访问该对象'
