"""认证后端 Provider（v1.7.7）。

`AUTHENTICATION_BACKENDS` 是**有序链**：`authenticate()` 逐个尝试，第一个返回用户的生效。
所以这里用「dotted path 列表」而不是主题 / 图表那种「目录 + 单 key 选择」——
单选引擎语义对有序链不适用；加一行 = 多一种登录方式。

模块职责：
- `validate_auth_backends(paths)`：纯函数契约校验（`apps.ready()` 只负责调它）。
  抽成纯函数的理由：`ready()` 每个进程只跑一次，`override_settings` 不会重新触发它，
  写在 `ready()` 里的校验**测试测不到**。
- `UsernameOrEmailBackend`：无外部依赖的示例 Provider（见 `username_or_email.py`）。
"""
