# 插件开发文档：v1.7.11 匿名 JSON 401 + 残留功能级 302 收口

> 关联：`plugin_host/middleware.py`（`ExceptionGuardMiddleware._wants_json` / 新增 `JsonAwareLoginRequiredMiddleware`）、`plugin_host/settings.py`（MIDDLEWARE）、`plugins/attendance/views.py`（`attendance_check`）
> 版本：v1.7.11 · 文档日期：2026-11-11
> 状态：**✅ 已实现**（433 项测试；见 §六）
> 基线：tag `v1.7.10`（427 项测试）
> 前置决策（v1.7.9 收尾时你定的顺序）：对象级越权已完成，**匿名 JSON 401 排在其后**；HTML 的 302 语义不变。

## 一、两件事

### 1.1 匿名访问 JSON 接口：302 → 401

现状：`LoginRequiredMiddleware`（Django 内置）对匿名请求一律 `redirect_to_login`。前端 `fetch`
（`plugins/attendance/templates/.../attendance_records.html` 里的月度看板、blockchain stats 等）会
跟随 302 拿到登录页 HTML，然后在 `response.json()` 处炸掉——用户只看到「图表不可用」。

改法：**只对「要 JSON 的请求」返回 401 JSON**，其余保持 302 到登录页（v1.7.4 口径不动）。

```python
# plugin_host/middleware.py
def wants_json(request):
    """唯一的 JSON 判据：/stats 结尾或 Accept: application/json。"""
    accept = request.headers.get('Accept', '')
    return request.path.rstrip('/').endswith('/stats') or 'application/json' in accept


class JsonAwareLoginRequiredMiddleware(LoginRequiredMiddleware):
    """匿名 + 要 JSON → 401 {"code","message"}；其余交给内置中间件（302 + next）。"""

    def process_view(self, request, view_func, view_args, view_kwargs):
        response = super().process_view(request, view_func, view_args, view_kwargs)
        if response is None:
            return None
        if wants_json(request) and response.status_code == 302:
            return JsonResponse(
                {'code': 'authentication_required', 'message': '登录状态已失效，请重新登录'},
                status=401)
        return response
```

- `ExceptionGuardMiddleware._wants_json` 改为委托 `wants_json()`——**判据只有一份**（v1.7.9 的禁止项 #2 同款要求）。
- 中间件位置不变：仍排在 `AuthenticationMiddleware` 之后。
- 401 不放 `WWW-Authenticate`（会话式认证没有 challenge 语义，加了反而误导）。

### 1.2 残留的功能级 302：`attendance_check`

`plugins/attendance/views.py:88` 手写了 `has_perm('attendance_check')` → `redirect('index')`，
绕过了 `require_perm`，是 v1.7.9 之后**唯一残留的功能级 302**（其余 `redirect('index')` 是登录回跳/登出/SSO 入口，不是越权）。

改法：与 `require_perm` 同口径 —— `raise ObjectPermissionDenied('无权访问该功能')`。

## 二、不做 / 已知边界

- **不动 HTML 的 302**：匿名访问 HTML 页仍是 `302 → /plugins/auth/login/?next=…`（v1.7.4 的核心口径）。
- 不给 401 加 `WWW-Authenticate`；不引入 JSON 的 400/405 等其它语义。
- `logout_view` / `sso_entry` 里的 `redirect('index')` 不是越权（分别是登出跳转与「已登录就别看 SSO 入口」），不动。
- 不动 `require_perm` 本身。

## 三、测试记录（+6，427 → 433）

| # | 用例 | 断言 |
|---|---|---|
| 1 | 匿名 + `Accept: application/json` 访问受保护页 | **401**，body `{"code":"authentication_required","message":"登录状态已失效，请重新登录"}` |
| 2 | 匿名访问 `/plugins/blockchain/stats/`（路径式 JSON） | **401** JSON（不带 Accept 也成立） |
| 3 | 匿名访问 HTML 受保护页 | **302** 到登录页且带 `next`（回归保护） |
| 4 | 已登录无权限访问同一 JSON 接口 | **403**（不是 401，两者不串） |
| 5 | 权限冻结账号访问 `attendance_check` | **403** 品牌页（`attendance_check` 是全员基线权限，唯一会拒绝的真实状态是 `permission_frozen=True`） |
| 6 | `login_not_required` 的登录页本身 | 200（不被守卫误伤） |

## 四、验收方案

1. 容器 HTTP：匿名 `fetch` 等价请求（`Accept: application/json`）→ 401 JSON，前端 `response.ok === false` 且能解析；
2. 匿名 HTML → 302 + `next`（v1.7.4 口径不变）；
3. 已登录无权限 → 403（v1.7.9 口径不变）；
4. 门禁三条 + 全量 432；
5. `ExceptionGuardMiddleware` 的 JSON 判据与登录守卫共用 `wants_json()`（代码上只有一处）。

## 六、验收记录（2026-11-11）

### 6.1 容器 HTTP 冒烟

| 场景 | 结果 |
|---|---|
| 匿名 `GET /plugins/blockchain/stats/?days=7`（Accept json） | **401** `{"code": "authentication_required", "message": "登录状态已失效，请重新登录"}` |
| 匿名 `GET /plugins/structure/`（HTML） | **302**（v1.7.4 口径不变） |
| 已登录 + 权限冻结 + `Accept: application/json` | **403** `{"code": "permission_denied", "message": "无权访问该功能"}`（401 与 403 不串） |
| 权限冻结账号 `GET /plugins/attendance/check/?action=in` | **403** |

> 临时账号 `json_probe` 用完即删。

### 6.2 门禁

`ruff` / `check` / `makemigrations --check` 通过；**Ran 433 tests OK**（427 + 6）。

### 6.3 同步的既有断言（2 处）

| 用例 | 变化 |
|---|---|
| `tests_login_guard.LoginGuardConfigTests.test_middleware_config_position` | 断言换成 `JsonAwareLoginRequiredMiddleware`，并加 `issubclass(…, LoginRequiredMiddleware)`、位置仍在 `AuthenticationMiddleware` 之后 |
| `tests_login_guard.LoginGuardSetTests.test_guard_sets_are_pinned` | 运行时集合判定把 **401** 也算「被拦」，并校验 401 的 `code` 是 `authentication_required`（不是随便哪个 401） |

## 五、待办（不在本版）

1. 其他插件的对象级校验（`user.views` 的 `get_object_or_404` 系列）未扫尾——它们目前对「对象不存在」与「无权」
   的行为需要逐个判定，属独立一版。
2. 403/401 页面没有「申请权限 / 重新登录」入口，等产品决定。
