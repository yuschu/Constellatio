# 插件开发文档：v1.7.16 CSP（Content-Security-Policy）加固

> 关联：`plugin_host/csp.py`（新）、`plugin_host/settings.py`（MIDDLEWARE）、`plugin_host/urls.py`（handler500）、`plugin_host/static/js/confirm.js`（新）、13 处内联 `<script>`、6 处 `onclick`
> 版本：v1.7.16 · 文档日期：2026-11-12
> 状态：**✅ 已实现**（482 项测试；自动化判据全部通过，真机项见 §7）
> 基线：tag `v1.7.15`（472 项测试）

## 一、下发的策略（十指令）

```
default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'
```

### 1.1 为什么 `style-src` 是 `'unsafe-inline'`

全站 `style="…"` 内联样式属性：`plugins/` 下就有 **137 处**，`themes/`、`templates/` 更多，
其中包含图表容器的 `style="width:100%;height:320px"`。收紧到 `'self'` 会让图表高度塌成 0、
全站排版崩。**防护重心是脚本执行面**：`script-src` 严格 + `style-src` 放宽是业界通行取舍。
**不迁移**这 137 处（禁止项）。

### 1.2 为什么 `script-src` 不给 `'unsafe-inline'`

给了就等于这条 CSP 在脚本面零防护，nonce 形同虚设。所以必须把内联面改造掉：
内联 `<script>` 用 nonce，内联事件（`onclick`）用 `data-confirm` + 外部脚本。

### 1.3 nonce 为什么是唯一路线（而不是静态 hash）

`templates/includes/stats_fetch_fail.js` 被 `{% include %}` 进 `<script>` 后，内容里有
`{% url "auth:login" %}` 与 `{% trans %}` —— 同一份模板在不同主题/不同语言下渲染结果不同。
`'sha256-…'` 要求算 hash 的内容与浏览器执行的字节完全一致，这类带模板变量的内联脚本**无法给出稳定 hash**。
nonce 与内容无关，因此是唯一可行路线。

## 二、改动清单

### 2.1 中间件（`plugin_host/csp.py`）

- 每请求生成 nonce（`secrets.token_urlsafe(16)`），挂到 `request.csp_nonce`；
- 在 `__call__` 里**只生成一次**，模板用 `{{ request.csp_nonce }}` 读取同一个值
  （同一响应内所有 script 必须共用一个 nonce，禁止在模板/helper 里二次生成）；
- 响应阶段写 `Content-Security-Policy`；
- 位置：`settings.MIDDLEWARE` 中紧接 `SecurityMiddleware` 之后（所有项目中间件之前）。
  响应阶段自下而上，放最外层才能保证 `ExceptionGuardMiddleware` 渲染的 400/403 也带 CSP 头；
- `/static/` 响应**不加** CSP（`CspMiddleware` 里按 `STATIC_URL` 前缀跳过）；
- 硬 500：Django 默认 500 在**中间件链之外**生成，`__call__` 的响应阶段拿不到它，
  因此由 `handler500 = 'plugin_host.csp.server_error'` 补头（nonce 复用 `request.csp_nonce`）。

### 2.2 13 处内联 `<script>` 加 nonce

统一写法 `<script nonce="{{ request.csp_nonce }}">`：

| 文件 | 行 |
|---|---|
| `plugins/approval/templates/approval/approval_detail.html` | 124 |
| `plugins/approval/templates/approval/approval_list.html` | 59 |
| `plugins/attendance/templates/attendance/attendance_dashboard.html` | 86 |
| `plugins/attendance/templates/attendance/attendance_records.html` | 229 |
| `plugins/blockchain/templates/blockchain/blockchain_list.html` | 104 |
| `plugins/structure/templates/structure/overview.html` | 120 |
| `plugins/workspace/templates/workspace/switch_list.html` | 54 |
| `plugin_host/templates/home_dashboard.html` | 252 |
| `templates/403.html` | 17 |
| `themes/corporate-clean/templates/base.html` | 81 |
| `themes/corporate-clean/templates/login.html` | 72 |
| `themes/risograph/templates/base.html` | 87 |
| `themes/risograph/templates/login.html` | 79 |

`templates/includes/stats_fetch_fail.js` 本身不加 nonce（它是 `.js` 片段，nonce 只加在包裹它的
`<script>` 标签上——即上表 252 / 104 / 86 / 229 四处）。

### 2.3 6 处内联 `<style>` 块：不改（记录备查）

`plugins/structure/templates/structure/overview.html:107`、`templates/500.html:9`、
`themes/corporate-clean/templates/base.html:17`、`themes/corporate-clean/templates/login.html:16`、
`themes/risograph/templates/base.html:17`、`themes/risograph/templates/login.html:16`
（其中 4 处在 `<noscript><style>` 内）。`style-src` 已放宽，无需改动。

### 2.4 6 处 `onclick` → `data-confirm`

| 文件 | 行 | 动作 |
|---|---|---|
| `plugins/user/templates/user/department_list.html` | 47 | 停用 |
| `plugins/user/templates/user/department_list.html` | 54 | 物理删除 |
| `plugins/user/templates/user/user_list.html` | 62 | 禁用 |
| `plugins/user/templates/user/user_list.html` | 69 | 冻结权限 |
| `plugins/user/templates/user/user_list.html` | 75 | 禁用 |
| `plugins/structure/templates/structure/template.html` | 18 | 应用模板 |

新增 `plugin_host/static/js/confirm.js`：监听 `submit` 捕获阶段，取 `event.submitter`（或表单内
`[data-confirm]`）的 `data-confirm` 文案，`confirm` 返回 false 就 `preventDefault()`。
两个主题的 `base.html` 各加 `<script src="{% static 'js/confirm.js' %}" defer></script>`。

## 三、admin 为什么不需要豁免

实测 Django admin 模板（`venv/Lib/site-packages/django/contrib/admin/templates`）：
内联 `<script>` **0**、`onclick` **0**、`style=` **0**；只有全同源的 `<script src>`，
由 `script-src 'self'` 覆盖。因此**不给 `/admin/` 开路径豁免**——开了豁免等于留一个
「以后往 admin 加内联也不会被发现」的口子。

## 四、ECharts 的 `new Function` 分析

`charts/echarts/static/vendor/echarts.min.js`（1 030 185 B）含 `new Function` 调用，
用于 `JSON.parse` 不可用时的回退路径；现代浏览器 `JSON.parse` 存在，**理论不触发**，故**不加**
`'unsafe-eval'`。

- **理论分析**：已做（见上）；
- **真机验证**：**未验证** —— 本环境无浏览器。真机判据见 §7；
- 若真机出现 `Refused to evaluate` / `unsafe-eval` 报错：**先如实上报**，不要自行加指令。

## 五、可自动化验收（实测，2026-11-12）

`plugin_host/tests_csp.py` 10 条用例，全部通过：

| 判据 | 结果 |
|---|---|
| `/`、`/plugins/auth/login/`、`/plugins/blockchain/`、`/admin/` 均带 CSP 头 | ✅ 头含 `nonce-` 与 10 条指令 |
| 同一响应内所有 `<script nonce>` 相同 | ✅ 首页只有 1 个内联 script 时也断言存在，值与头一致 |
| 连续两次请求 nonce 不同 | ✅ |
| 全仓模板 `onclick=` 为 0 | ✅（`grep` 遍历 `plugins/ plugin_host/ templates/ themes/`） |
| 6 个按钮改成 `data-confirm` | ✅ 模板级计数 2+3+1=6，且结构模板页渲染出 `data-confirm` |
| 4 个图表页的 `<script>` 带 nonce | ✅ 且页面内不再存在裸 `<script>` |
| 403（中间件链）带 CSP | ✅ |
| 硬 500（`handler500`）带 CSP | ✅ `DEBUG=False` + `Client(raise_request_exception=False)` |
| `/static/` 不发 CSP | ✅ 中间件单测（测试客户端不服务静态文件，故直接测跳过逻辑） |
| 门禁 | `check` / `ruff` / 全量 **482 项 OK**（472 + 10） |
| `check --deploy` | 生产语义配置下仍 `no issues`、exit=0 |

## 六、不做（原样保留）

- **不加** `'unsafe-eval'`。
- **不给 `/admin/` 开豁免**。
- **不迁移** 137 处 `style=` 属性。
- **不给 `script-src` 加 `'unsafe-inline'`**。
- **不改** `X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy`。
- **不动** `SECRET_KEY` / compose / Bootstrap 离线化（v1.7.15 已收口）。
- **不新增运行时依赖**（自写中间件，无 `django-csp`）。

## 七、真机待验（评审者执行，本文档不声称已完成）

1. 两个主题下打开 4 个图表页（`/`、`/plugins/blockchain/`、`/plugins/attendance/records/`、`/plugins/attendance/`），图表正常渲染；
2. 浏览器控制台零 CSP 报错（尤其无 `Refused to evaluate` / `unsafe-eval`）；
3. 6 个 `data-confirm` 按钮：确认执行、取消不发请求；
4. 401 / 403 降级逻辑（v1.7.12 三项）回归正常。

## 八、已知遗留

1. `confirm.js` 依赖 `event.submitter`（现代浏览器均支持；Safari < 15.4 会退化为「表单内第一个
   `[data-confirm]`」，这些页面每个表单只有一个确认按钮，行为不变）。
2. 内联 `<style>` 与 `style=` 属 `style-src 'unsafe-inline'` 的接受面，不是缺口。
3. CSP 没有 `report-uri`/`report-to`：本版只做阻断，不做上报收集。
