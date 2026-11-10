"""示例认证 Provider：用户名或邮箱都可登录（无外部依赖，v1.7.7）。

它证明 `OA_AUTH_BACKENDS` 的契约可用，同时不引入任何新依赖。
注意两处安全细节，都是权限绕过红线：
1. 必须过 `user_can_authenticate(user)`（`is_active` 检查）——自定义后端只做
   「查到用户就返回」会让**被禁用的用户直接登录**；
2. 用户不存在时跑一次默认密码哈希（`UserModel().set_password(password)`），
   与 `ModelBackend.authenticate()` 同款，缩小响应时间差。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()


class UsernameOrEmailBackend(ModelBackend):
    """先按 username 精确匹配，未命中再按 email（大小写不敏感）匹配。"""

    def _find_user(self, identifier):
        manager = UserModel._default_manager
        user = manager.filter(**{f'{UserModel.USERNAME_FIELD}': identifier}).first()
        if user is not None:
            return user
        return manager.filter(email__iexact=identifier).first()

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        identifier = str(username).strip()
        user = self._find_user(identifier)
        if user is None:
            # 与 ModelBackend 一致：跑一次哈希，减小「用户不存在 / 密码错」的响应时间差
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
