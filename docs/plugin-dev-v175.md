# 插件开发文档：v1.7.5 错误页 + 日志与异常分类

> 关联：容器（settings / middleware / templates / exceptions）、attendance 与 blockchain 的 JSON 接口
> 版本：v1.7.5 · 文档日期：2026-11-10
> 状态：**第一步（错误页模板）已实现；第二步（日志与异常分类）方案待确认**
> 基线：tag `v1.7.4`（368 项测试全绿）；第一步交付后 **372 项**
> 编号说明：v1.7.5 原排「认证后端插件化 + 限流计数原子化 P2」，本版改为本项 → 两项顺延 **v1.7.6**（P2 仍第一项），改号原因随后同步到 roadmap。

## 一、问题

- `settings.py` 无 `LOGGING`：MySQL 重启导致 500 时，容器日志只有 Django 默认 traceback 片段，没有 request_id、没有请求上下文，运维无法把「用户投诉的那次」对应到「日志里那一坨」。
- 没有 `templates/400|403|404|500.html`：所有异常都是 Django 默认页，不带品牌、不带下一步动作，用户看到的是「Using the URLconf defined in …」或者纯文本 `Server Error (500)`。

## 二、第一步：错误页模板（已实现）

### 2.1 框架事实（`inspect` 现读 Django 5.2.18）

| handler | 模板 | 渲染方式 | 可用上下文 |
|---|---|---|---|
| `page_not_found` | `404.html` | `template.render(context, request)` | `request_path`、`exception`，**request 可用 → 上下文处理器会跑** |
| `permission_denied` | `403.html` | `template.render(request=request, context={'exception': ...})` | `exception`（字符串），request 可用 |
| `bad_request` | `400.html` | `template.render(request=request)` | 无（刻意不喂异常内容，防泄漏） |
| `server_error` | `500.html` | **`template.render()`（空上下文、无 request）** | **无** |

结论：DEBUG=False 时 Django 默认 handler 自动渲染同名模板，**不需要写 handler 函数、不需要改 URLconf**（与需求一致）。但 500 页必须自给自足——不能依赖 `request`/上下文处理器。

### 2.2 唯一一处「不只是模板」的改动：模板搜索路径

本项目 `TEMPLATES` 是 `APP_DIRS=False` + 显式 `loaders`（v1.5.8 为运行时换肤引入），`DIRS` 原本为空，`ThemeLoader` 只查「当前主题的 templates 目录」。因此**容器根 `templates/404.html` 默认根本找不到**，会静默回退成 Django 默认页。改动（`plugin_host/settings.py`）：

- `DIRS = [BASE_DIR / 'templates']`
- `loaders` 在 `ThemeLoader` 之后插入 `django.template.loaders.filesystem.Loader`（显式 loaders 下 `DIRS` 只有靠它才生效）

顺序保持「主题模板 → 容器模板 → 插件 app 模板」，不改变既有主题优先级。

### 2.3 四个模板的设计

| 文件 | 写法 | 理由 |
|---|---|---|
| `templates/404.html` | `{% extends "base.html" %}` | handler 传 request，上下文处理器可用 → 完整外壳（品牌 + 侧栏 + 返回工作台按钮） |
| `templates/403.html` | 同上 | 同上；**不渲染 `exception` 文本**（避免把内部异常内容回显给用户） |
| `templates/400.html` | 同上 | 同上；handler 不喂上下文，页面用固定文案 |
| `templates/500.html` | **独立页面**（不 extends） | `server_error` 用空上下文渲染，`base.html` 依赖的 `plugins_enabled` / `menu` / `request` 全缺 → 一旦模板报错，Django 会退化成纯文本 `Server Error (500)`。独立页面用内联 `<style>`（只有 CSS，无 JS，符合规约）+ `{% static %}` 不依赖任何上下文变量 |

文案统一为：品牌（Constellatio · 企业办公自动化）→ 错误码（400/403/404/500）→ 一句话说明 → 「返回工作台」按钮。

### 2.4 i18n

新增 11 条 msgid 写入 `locale/en/LC_MESSAGES/django.po` 并执行 `tools/compile_mo.py`（`.mo` 不入库）。有一条用例专门断言英文下 500 页出现 `Server error` / `Back to workspace`，防止文案漏翻。

### 2.5 测试（新增 4 条，`plugin_host/tests_error_pages.py`）

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_404_renders_branded_page` | DEBUG=False 下 `/no-such-page-for-test/` → 404，含品牌 / 404 / 返回工作台，且**不含** `Using the URLconf defined in` |
| 2 | `test_500_renders_branded_page_without_stack` | 直调 `defaults.server_error()` → 500，含品牌 / 500 / 返回按钮；断言不含 `Traceback`、`RuntimeError`、`File "`、`django/` |
| 3 | `test_403_and_400_render_branded_pages` | 直调 `permission_denied` / `bad_request`（补 `request.user`）→ 403/400 品牌页；403 不含传进去的异常文本 |
| 4 | `test_error_pages_are_translated` | `translation.override('en')` 下 500 页出现 `Server error` / `Back to workspace` |

### 2.6 验收记录（第一步）

- 门禁：`check` 无问题 / `ruff` All checks passed / **Ran 372 tests OK**（368 + 4）。
- 容器（`DJANGO_DEBUG=0`，实测容器内 `settings.DEBUG = False`）：`GET /no-such-page/` → **404，含品牌 / 404 / 返回工作台，不含 Django 默认页特征**。
- 500 页在本地 handler 直测渲染通过；**容器级 500 冒烟依赖第二步**（需要一个会抛异常的视图），届时一起补。

## 三、第二步方案（待确认后再实现）

### 3.1 `LOGGING`（settings）

```python
LOG_DIR = BASE_DIR / 'logs'          # 本地；*.log 已被 .gitignore 覆盖
LOG_TO_FILE = os.environ.get('DJANGO_LOG_TO_FILE', '1') == '1'
```
- `formatters.verbose`：`%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s`
- `filters.request_id`：读 contextvar，缺省 `-`（非请求上下文：shell / 启动期）
- `handlers`：`console`（StreamHandler，容器主通道）+ `file`（`RotatingFileHandler`，`logs/constellatio.log`，5MB × 5）
- `loggers`：`django`(INFO)、`plugins`(INFO)、`plugin_host`(INFO)→ 两个 handler；`django.request`(WARNING) 保留；root WARNING → console
- 待确认：容器里是否默认也写文件（`DJANGO_LOG_TO_FILE=0` 可关）。倾向默认开，容器内 `/app/logs` 可写，日志卷不进 git。

### 3.2 `request_id`

- 新增 `plugin_host/middleware.py: RequestIdMiddleware`：`uuid4().hex[:8]`，放 `SecurityMiddleware` 之后（**最外层之一**，保证 500 也有号）；`__call__` 里 set contextvar → `get_response` → `response['X-Request-Id'] = rid` → finally reset。
- 日志 filter 从 contextvar 取，避免 threading 串号；shell / 管理命令下为 `-`。
- 500 页文案再把「把响应头里的 X-Request-Id 报给管理员」加回来（第一步先写的是「请联系管理员」，避免承诺尚不存在的响应头）。

### 3.3 `plugin_host/exceptions.py`

```python
class BusinessError(Exception):          # 业务校验失败 → 400
    status_code = 400
    code = 'business_error'
    def __init__(self, message, code=None): ...

class ObjectPermissionDenied(PermissionDenied):   # 对象级越权 → 403
    code = 'permission_denied'
```
`ObjectPermissionDenied` 继承 Django `PermissionDenied`：即使某条路径没走到我们的中间件，Django 也会用 `403.html` 兜底（与第一步的模板天然咬合）。

### 3.4 `ExceptionGuardMiddleware.process_exception`

```python
def process_exception(self, request, exception):
    try:
        if isinstance(exception, BusinessError):
            logger.warning('业务校验失败 code=%s %s', exception.code, exception)   # 含 request_id
            return _error_response(request, 400, exception.code, str(exception))
        if isinstance(exception, (ObjectPermissionDenied, PermissionDenied)):
            logger.warning('越权 code=%s %s', code, exception)
            return _error_response(request, 403, code, msg)
        logger.exception('未处理异常 %s %s', request.method, request.get_full_path())  # 完整栈
        return None      # 交回 Django → 默认 500 处理器 → templates/500.html
    except Exception:
        logger.exception('ExceptionGuardMiddleware 自身失败（已降级为默认处理）')
        return None
```
- 自身用 `try` 包住，任何失败只记日志、`return None`，绝不外抛（避免错误处理器再炸一次）。
- 位置：`LoginRequiredMiddleware` 之后、`MessageMiddleware` 之前即可（`process_exception` 逆序执行，不需要特别靠外）。

### 3.5 JSON 接口错误体统一

- 判定：`request.path` 以 `/stats/` 结尾，或 `Accept` 含 `application/json` → `JsonResponse({'code': ..., 'message': ...}, status=...)`；否则渲染 `400.html`/`403.html` 并把 message 传进模板（`400.html` 增一个可选 `message` 显示块）。
- **契约变更**：`attendance_stats` 与 `blockchain_stats` 现在的错误体是 `{'error': 'invalid_month' | 'invalid_days'}`，要改成 `{'code': ..., 'message': ...}`。已确认**前端没有消费 `error` 字段**（`grep` 模板/JS 为空），但**有 3 处既有测试断言**要随契约更新：
  - `plugins/attendance/tests.py:244` → `response.json()['error'] == 'invalid_month'`
  - `plugins/blockchain/tests.py:140-145` → `['error'] == 'invalid_days'`（两处 subTest）
  这是**契约变更导致的断言改写**，不是「为了让测试变绿改断言」，会在提交信息里单独注明。若你希望零改动，可改为「保留 `error` 字段 + 新增 `code`/`message`」的兼容方案（两套形状并存，不推荐）。

### 3.6 第二步测试计划（预计 +6，372 → 378）

| # | 用例 | 断言 |
|---|---|---|
| 5 | `test_business_error_returns_400_with_message` | 触发 `BusinessError('库存不足')` → 400，页面/JSON 里 message 原样出现 |
| 6 | `test_object_permission_denied_returns_403` | 触发 `ObjectPermissionDenied` → 403 |
| 7 | `test_unhandled_error_logs_stack_and_returns_500` | `assertLogs('plugin_host', 'ERROR')` + 500 页无栈；日志含 `Traceback` 与 `request_id` |
| 8 | `test_request_id_header_on_success_and_error` | 200 与 500 响应都带 `X-Request-Id`，且长度 8 |
| 9 | `test_stats_endpoint_error_body_shape` | `/plugins/blockchain/stats/?days=0` → 400，JSON 只有 `code`/`message` |
| 10 | `test_guard_failure_does_not_escape` | monkeypatch 让 guard 内部抛异常 → 仍返回 500、只记日志、不外抛 |

需要新增测试夹具 `plugin_host/tests_urls_error.py`（只有会抛异常的视图，用 `override_settings(ROOT_URLCONF=...)` 挂载），避免为了测试往生产 URLconf 塞视图。

## 四、不做 / 边界

- 不改 `DEBUG` 默认值（加固包的事）；不在错误页写内联 JS（500 页只有内联 CSS）。
- 不写 `handler400/403/404/500` 自定义函数（默认 handler 已够；写了反而多一处要维护的渲染路径）。
- 不做 Sentry/APM 等外部上报（无新依赖）。
- **`template.render()` 的字符串不得来自用户输入**——404 页里 `request_path` 目前只用于服务端拼 HTML，模板中未回显异常内容；后续若要显示「你访问的路径」，必须用 `{{ request_path }}`（Django 会转义），不能 `|safe`。

## 五、待办观察（不在本版修）

1. `404.html` 等三页 `extends base.html`，会跑上下文处理器（含 `notifications` 查库）。**DB 不可用时 404 页本身可能渲染失败退化为 500**；500 页是独立的，不受影响。若认为这条不可接受，可改成三页也不依赖上下文（代价是没有侧栏外壳）。
2. 第一步交付的 500 页文案暂为「如需协助，请联系管理员」，因为 `X-Request-Id` 响应头要到第二步才存在——第二步实现后回填。
3. v1.7.5 原排的「认证后端插件化 + P2 计数原子化」顺延 v1.7.6，roadmap 改号时按既有先例写明让位原因。
