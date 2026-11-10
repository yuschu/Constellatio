# 插件开发文档：v1.7.5 错误页 + 日志与异常分类

> 关联：容器（settings / middleware / templates / exceptions）、attendance 与 blockchain 的 JSON 接口
> 版本：v1.7.5 · 文档日期：2026-11-10
> 状态：**✅ 已实现**（两步都落地：错误页模板 + 日志/request_id/异常分类，380 项测试全绿）
> 基线：tag `v1.7.4`（368 项）；第一步 372 项；第二步完成 **380 项**（+8）
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

## 三、第二步：实现记录（已落地）

### 3.1 `LOGGING`（settings，已落地）

```python
LOG_DIR = BASE_DIR / 'logs'          # 本地；*.log / logs/ 已被 .gitignore、.dockerignore 覆盖
LOG_TO_FILE = os.environ.get('DJANGO_LOG_TO_FILE', '0') == '1'   # 默认 0：容器只走 console
```
- `formatters.verbose`：`%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s`
- `filters.request_id`：**优先级 `record.request.request_id` > contextvar > `-`**（见 3.2 的时序坑）
- `handlers`：`console`（StreamHandler）常开；`file`（`RotatingFileHandler`，`logs/constellatio.log`，5MB × 5）
  **仅在 `LOG_TO_FILE=1` 时拼进字典**——`dictConfig` 会把 `handlers` 里定义过的每一个都实例化，即便没有 logger 引用它，
  写死字典会让容器在 `LOG_TO_FILE=0` 时照样建日志文件（实测踩过）
- `loggers`：`django`(INFO)、`django.request`(WARNING)、`plugins`(INFO)、`plugin_host`(INFO)；
  **`plugins` / `plugin_host` 保持 `propagate=True`**，root **不配 handler**
- **推论（Django 默认行为，不是本版选择）**：`root {'level': 'WARNING'}` 意味着第三方库的 INFO 被丢弃；
  `logging.lastResort` 只在「整条链上一个 handler 都没找到」时才出手，兜的是**完全未配置**的 WARNING 及以上。
  本项目里 `plugins` / `plugin_host` 自己有 handler，`callHandlers` 的 `found` 已 > 0，不会再触发 `lastResort`，
  所以既不会重复输出，`assertLogs()`（默认挂 root）也仍能收到记录。
- 轮转策略：容器 3 worker **不写文件**（多进程各自 rotate 同一文件会丢日志/写进已改名的旧文件），轮转交给
  docker 日志驱动或宿主 `logrotate`；本地 runserver 单进程才开文件。

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
            logger.warning('业务校验失败 code=%s msg=%s', exception.code, exception)
            return self._error_response(request, 400, exception.code, exception.message)
        if isinstance(exception, (ObjectPermissionDenied, PermissionDenied)):
            logger.warning('拒绝访问 code=%s %s %s', code, request.method, request.get_full_path())
            return self._error_response(request, 403, code, '无权访问该对象')
        logger.exception('未处理异常 %s %s', request.method, request.get_full_path())
        return None      # 交回 Django → 默认 500 处理器 → templates/500.html
    except Exception:
        logger.exception('ExceptionGuardMiddleware 自身失败，已降级为默认处理')
        return None
```
- 自身用 `try` 包住，任何失败只记日志、`return None`，绝不外抛（避免错误处理器再炸一次）。
- **位置写死为 `Security → RequestId → ExceptionGuard → …`**：Guard 在 RequestId 之内，兜底日志里的
  request_id 一定已存在；响应头由外层 RequestId 最后补上。反过来（Guard 在外）兜底日志会记成 `-`，排障对不上号。
- 边界：`process_exception` 只接得住「视图执行期间」的异常。`RequestIdMiddleware` 自身 `__call__` 前段、
  以及 `SecurityMiddleware` 的异常它接不到，那些落到 Django 最后的 `response_for_exception`（不额外加中间件）。
- **栈只记一次**：未预期异常走 `logger.error('未处理异常 %s: %s ...')`（**不带 exc_info**），完整栈由
  `django.request` 的 ERROR 记一次（`log_response` 对 5xx 必带 `exc_info`）。原先 guard 里用 `logger.exception`
  会让同一次 500 打两条完整栈——已改并有用例钉住（`test_unhandled_error_logs_once_with_single_stack`）。
  400/403 的两条 warning 保留：记的是**业务原因**，`django.request` 只记状态码，信息不重复。

### 3.5 JSON 接口错误体统一

- 判定：`request.path` 以 `/stats/` 结尾，或 `Accept` 含 `application/json` → `JsonResponse({'code': ..., 'message': ...}, status=...)`；否则渲染 `400.html`/`403.html` 并把 message 传进模板（`400.html` 增一个可选 `message` 显示块）。
- **契约变更（已落地）**：`attendance_stats` 与 `blockchain_stats` 原错误体 `{'error': 'invalid_month' | 'invalid_days'}` 已改成
  `{'code': ..., 'message': ...}`。前端没有消费 `error` 字段（`grep` 模板/JS 为空），但有 3 处既有断言随契约更新，
  并各加一条反向断言 `assertNotIn('error', payload)` 防止将来「兼容」回退成两套形状：
  - `plugins/attendance/tests.py:244` → `response.json()['error'] == 'invalid_month'`
  - `plugins/blockchain/tests.py:140-145` → `['error'] == 'invalid_days'`（两处 subTest）
  这是**契约变更导致的断言改写**，不是「为了让测试变绿改断言」，会在提交信息里单独注明。若你希望零改动，可改为「保留 `error` 字段 + 新增 `code`/`message`」的兼容方案（两套形状并存，不推荐）。

### 3.6 第二步测试（实际 +8，372 → 380）

`plugin_host/tests_exception_guard.py`，三个开关全部写死：`Client(raise_request_exception=False)`、
`override_settings(DEBUG=False)`、夹具 URLconf。

| # | 用例 | 断言 |
|---|---|---|
| 9 | `test_business_error_returns_400_with_message` | 400 页面来自 `templates/400.html`：品牌在、`400` 在、message 原样在、无栈 |
| 10 | `test_object_permission_denied_returns_403` | 403 页面来自 `templates/403.html`：品牌在、`权限不足` 在、**不回显 exception 文本** |
| 11 | `test_stats_path_gets_json_error_body` | 路径以 `/stats` 结尾时错误体 `{code,message}`，`assertNotIn('error', payload)` |
| 12 | `test_unhandled_error_logs_stack_and_returns_500` | 500 页含品牌、无 `Traceback`、无异常原文；`assertLogs('plugin_host','ERROR')` 里存在带 `exc_info` 的记录 |
| 13 | `test_request_id_header_on_success_and_error` | 200 与 500 都带 8 位 `X-Request-Id`，两次不同 |
| 14 | `test_guard_failure_does_not_escape` | monkeypatch `_error_response` 抛异常 → 仍返回 500 页面，不外抛 |
| 15 | `test_prefers_request_attribute` | filter 取 `record.request.request_id`（4xx/5xx 日志发生在中间件返回之后） |
| 16 | `test_falls_back_to_contextvar_then_dash` | 无 request 时取 contextvar，请求外为 `-`，reset 后不串号 |

夹具 `plugin_host/tests_urls_error.py` 用 `override_settings(ROOT_URLCONF=...)` 挂载，不往生产 URLconf 塞视图。
**夹具必须把真实 URLconf `include` 进来**：错误页模板里有 `{% url 'index' %}` / `{% url 'theme_switch' %}` /
`{% url 'language:language_switch' %}`，夹具若不提供这些名字，404 页渲染会抛 `NoReverseMatch` 变成 500，把用例带偏（实测踩过）。

## 四、不做 / 边界

- 不改 `DEBUG` 默认值（加固包的事）；不在错误页写内联 JS（500 页只有内联 CSS）。
- 不写 `handler400/403/404/500` 自定义函数（默认 handler 已够；写了反而多一处要维护的渲染路径）。
- 不做 Sentry/APM 等外部上报（无新依赖）。
- **`template.render()` 的字符串不得来自用户输入**——404 页里 `request_path` 目前只用于服务端拼 HTML，模板中未回显异常内容；后续若要显示「你访问的路径」，必须用 `{{ request_path }}`（Django 会转义），不能 `|safe`。

## 五、第二步验收记录（2026-11-10）

### 5.1 回报点（LOGGING + RequestIdMiddleware 落地后）

| 检查项 | 实测 |
|---|---|
| 容器内 handler 配置 | `LOG_TO_FILE=False`、`handlers=['console']`、`/app/logs` 不存在 |
| 真实 HTTP 404 | 响应头 `X-Request-Id: a05d86ed`；`docker logs` 里 `WARNING django.request [a05d86ed] Not Found: /no-such-page/` |
| 真实 500（把 `constellatio_cache` 临时改名，模拟 MySQL 故障 → 登录限流读缓存失败） | 响应头 `39ef4047`；日志 `ERROR django.request [39ef4047] Internal Server Error: /plugins/auth/login/` + **完整 Traceback（到 mysql/base.py）**；500 页含品牌、不含栈；`/app/logs` 仍不存在 |
| 恢复缓存表后同一 POST | 200「用户名或密码错误」 |

### 5.2 全量验收

- 门禁：`check` 无问题 / `ruff` All checks passed / **Ran 380 tests OK**（368 → 372 → 380）。
- 容器（`DJANGO_DEBUG=0`，3 worker）：登录后 `GET /plugins/blockchain/stats/?days=0` →
  `400 {"code": "invalid_days", "message": "时间窗口应为 1–90 天"}`，`keys=['code','message']`、`含 error=False`、带 `X-Request-Id`。
- 400 / 403 的**生产触发点**：目前只有测试夹具里的视图会抛 `BusinessError` / `ObjectPermissionDenied`
  （见 §六 第 4 条），所以这两条走的是用例验证而不是容器 HTTP 冒烟。
- **一次 500 只有一条完整栈**（收尾修正后实测）：日志流里 `plugin_host` 记
  `ERROR 未处理异常 RuntimeError: boom for test (GET /boom/)`（无栈），`django.request` 记
  `ERROR Internal Server Error: /boom/` + 唯一一条 `Traceback`；两条都带同一 `request_id`。

## 六、待办观察（不在本版修）

1. `404.html` 等三页 `extends base.html`，会跑上下文处理器（含 `notifications` 查库）。**DB 不可用时 404 页本身可能渲染失败退化为 500**；500 页是独立的，不受影响。若认为这条不可接受，可改成三页也不依赖上下文（代价是没有侧栏外壳）。
2. 第一步交付的 500 页文案暂为「如需协助，请联系管理员」，因为 `X-Request-Id` 响应头要到第二步才存在——第二步实现后回填。
3. v1.7.5 原排的「认证后端插件化 + P2 计数原子化」顺延 v1.7.6，roadmap 改号时按既有先例写明让位原因。
4. **越权反馈语义统一（302 / 403 / 404 三选一）——单独立项，排在 v1.7.6 之后**：
   今天 43 处装饰器 + 42 条 URL 的越权反馈统一是「302 回工作台」，`BusinessError` / `ObjectPermissionDenied`
   只有测试夹具在抛。**不做局部迁移**：只把审批详情/附件下载迁到 403 会造出「同一个用户被拒，有时回工作台、
   有时看到 403 页」的第二种反馈——正是 v1.7.4 刚花 7 处代码修掉的那类不一致。
   三种语义的取舍是需要产品决策的，决定后再一次性迁移：302（不泄漏对象是否存在）/ 403（泄漏「对象存在但无权」，
   便于用户知道找谁要权限）/ 404（完全不泄漏，适合对外接口）。`BusinessError` 的真实抛点（如「审批重复提交」
   「补卡超窗口」）与它同批做，避免两次改响应形状和用例。
5. **测试输出会带日志**：console handler 在跑测试时同样生效，404/500 用例会往 stderr 打 WARNING/ERROR。
   如需安静，可在测试配置里把 `django.request` 降级——但会降低「日志链路本身被测到」的可见性，本版不动。
6. **`logs/` 与 `*.log` 已进 `.gitignore` / `.dockerignore`**：本地 `DJANGO_LOG_TO_FILE=1` 产生的日志不会被打进镜像
   （实测镜像里 `/app/logs` 不存在；`.dockerignore` 补了 `**/*.log` 与 `logs/`，原先只有 `*.log` 漏了子目录）。
