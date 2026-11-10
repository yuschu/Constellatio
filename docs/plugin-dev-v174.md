# 插件开发文档：v1.7.4 登录守卫中间件化（框架默认拦截 + 显式白名单）

> 关联：容器 `MIDDLEWARE`（plugin_host/settings.py）、`plugin_host/middleware.py`、插件 auth / sso / language
> 版本：v1.7.4 · 文档日期：2026-11-10
> 状态：**✅ 已实现**（368 项测试全绿 + 3 worker 容器验收；`next` 回跳缺口已在收尾提交修复，见 §八 第 3、6 条）
> 基线：v1.7.3（tag `v1.7.3`，357 项测试全绿，Django 5.2.18）
> 编号说明：v1.7.4 原排「认证后端插件化 + 限流计数原子化 P2」，本版改为此项，故 P2 与认证后端插件化一并顺延为 **v1.7.5**（P2 仍是 v1.7.5 第一项）。若编号要另定，请指出。

## 一、需求

把「逐视图挂装饰器」改成「框架默认拦截 + 显式白名单」：任何视图默认要求登录，只有显式标注的 6 个匿名入口放行。

## 二、复核（框架事实与现状，均现读源码/现跑脚本）

### 2.1 框架事实（Django 5.2.18，`inspect.getsource` 原文）

| 事实 | 原文要点 |
|---|---|
| 中间件判定 | `process_view`：`request.user.is_authenticated` → 放行；`not getattr(view_func, "login_required", True)` → 放行；否则 `handle_no_permission` → `redirect_to_login(path, LOGIN_URL, redirect_field_name='next')` |
| 白名单机制 | `login_not_required(view_func)` 只做一件事：`view_func.login_required = False`；没有任何「放行列表」设置项 |
| `login_required` 不会置该属性 | `user_passes_test` 只设置 `_view_wrapper.login_url` 与 `redirect_field_name`，**不设 `login_required`**；所以「有装饰器」不等于「属性为 True」，两者互不干扰 |
| `next` 生成 | `build_absolute_uri` 与 LOGIN_URL 同 scheme/netloc 时用 `get_full_path()`，即带查询串的原路径 |
| admin 登录已自带豁免 | `admin.site.login.login_required` 实测为 `False`（`AdminSite.login` 已加 `login_not_required`），无需我们处理 |
| 版本要求 | `LoginRequiredMiddleware` 自 Django 5.1 起提供；本项目 5.2.18 满足 |

**推论**：`require_perm` 里的 `login_required` 与中间件不冲突——匿名请求在 `process_view` 阶段就被中间件拦下，走不到视图；已登录请求照旧走 `require_perm` 的权限码判定。

### 2.2 现状盘点（脚本枚举 `get_resolver()`，共 84 条 URLPattern）

| 分类 | 条数 | 说明 |
|---|---|---|
| admin | 35 | 含 `admin/login/`（Django 已标 `login_required=False`） |
| 非 admin | 49 | |
| 非 admin 且受 `user_passes_test` 族装饰器保护（`hasattr(callback, 'login_url')`） | 42 | 中间件上线后行为不变 |
| 非 admin 且**无任何登录守卫** | **7** | 见下表，其中 6 条必须进白名单 |

无守卫的 7 条：

| # | URL | 视图 | 处置 | 理由 |
|---|---|---|---|---|
| 1 | `/plugins/auth/login/` | `auth.views.login_view` | **白名单** | 否则无限重定向 |
| 2 | `/plugins/auth/logout/` | `auth.views.logout_view` | **白名单** | 未登录点退出不该跳登录页 |
| 3 | `/plugins/auth/password-reset/` | `auth.views.password_reset_notice` | **白名单** | 登录页「忘记密码」入口，占位页 |
| 4 | `/plugins/language/switch/` | `language.views.language_switch` | **白名单** | 登录页顶部就是中英切换表单（`themes/*/templates/login.html:23` 直接 POST 到它），漏掉=按钮静默失效且现有测试不会红 |
| 5 | `/plugins/sso/login/` | `sso.views.sso_login_view` | **白名单** | SSO 表单页（GET 展示 / POST 提交 Ticket，表单无 action→提交回本 URL），漏掉=SSO 登录整体不可用 |
| 6 | `/plugins/sso/` | `sso.views.sso_entry` | **白名单** | 登录页「企业 SSO 登录」按钮指向此处（`login.html:58`）；登录后访问会 302 回工作台 |
| 7 | `/theme/switch/` | `plugin_host.views.theme_switch` | **不进白名单** | 换肤表单只存在于 `themes/*/templates/base.html`（登录后的外壳）；`login.html` 是独立页面、无换肤按钮（实测 `grep -c theme_switch login.html` = 0）。匿名 POST 将改为 302 到登录页，属预期收敛 |

> 与任务清单的差异（两处，需确认）：①SSO 是**两个**视图（`sso_login_view` 与 `sso_entry`），只白名单「门户入口」会让 `/plugins/sso/login/` 失效；②白名单实际是 **6 个视图 / 6 条 URL**，另有 `theme/switch/` 保持受保护。

### 2.3 装饰器实数（任务里写「19 处」，已核实为历史快照，作废）

```
$ grep -rc "@require_perm"  plugins/*/views.py
approval 5 | attendance 4 | blockchain 3 | notice 2 | notify 3 | structure 4 | user 8 | workspace 2   → 31
$ grep -rc "@login_required" plugins/*/views.py plugin_host/views.py
approval 2 | attendance 2 | notice 2 | user 4 | plugin_host 1                    → 12
```

合计 **43 处 = 42 条视图守卫 + 1 处非视图用法**（`plugin_host/permissions.py:19` 的
`@login_required` 是 `require_perm` 内部对 wrapper 的保护，不对应独立 URL）。受保护的非 admin URL 为 42 条。

「19」的可复现来源（负责人核对）：v1.7.0 时代只统计 `@login_required` / `@permission_required`
——`attendance 3 + permissions.py 3 + approval 3 + plugin_host/views.py 2 + notice 3 + user/views 5 = 19`；
v1.7.1 的 P0-C 授权批次补入大批 `@require_perm` 后总量变为 43。**本版以 43 为准，一处不删**。

### 2.4 静态文件（任务第 3 条）：经核实**不适用**，不改代码

- 根 `urls.py` 与各插件 `urls.py` 里**没有** `static()` / `staticfiles_urlpatterns()`（`grep` 为空）。
- 本地 `DEBUG=True` 时，`runserver` 的 `StaticFilesHandler` 在 **WSGI 层**就直出 `/static/`，不进入 URL 解析与中间件栈。
- 容器内 `WhiteNoiseMiddleware` 位于 `MIDDLEWARE` 第 2 位（`SessionMiddleware` 之前），同样在 `process_view` 之前直出静态。
- 因此「`static()` 视图被拦」在当前代码下不会发生；为防将来有人往 `urls.py` 塞 `static()`，用**全量扫描测试**兜住（见 §五 第 6 条：若出现匿名可达的 `django.views.static.serve` 且未标白名单，测试变红）。

## 三、设计口径（契约）

| 项 | 决策 |
|---|---|
| 默认策略 | 全局默认「必须登录」，白名单只有 6 个匿名入口；新增视图默认受保护，**忘记标注的后果是「被拦」而不是「裸奔」** |
| 白名单写法 | `from django.contrib.auth.decorators import login_not_required` + `@login_not_required`，**统一放装饰器链最外层**。技术事实：`functools.wraps` 会复制 `__dict__`，而 `login_not_required` 设的就是 `__dict__` 里的 `login_required=False`，所以放内层理论上也生效；仍按最外层执行，理由是**语义明确、不依赖 `wraps` 的 `__dict__` 复制行为**（否则将来有人看到「内层也能跑」就挪进去，再叠一层不复制 `__dict__` 的装饰器会静默失效） |
| 中间件位置 | `'django.contrib.auth.middleware.LoginRequiredMiddleware'` 逐字插入 `AuthenticationMiddleware` 之后、`MessageMiddleware` 之前 |
| 与插件停用的关系 | `PluginRouteGuardMiddleware` 是 `__call__` 型（不是 `process_view`），在整条链最外层（第 7 位），停用插件的请求先 404、不会被登录跳转抢走 |
| admin | 不动：`admin/login/` 由 Django 自行豁免；其余 admin 页匿名访问 → 跳登录（`next` 带回），与原生行为一致 |
| 装饰器 | 43 处全保留；`require_perm` 内的 `login_required` 保留（双重守卫，口径一致：中间件管「登没登录」，`require_perm` 管「有没有权限码」） |
| 禁止 | 不写 `LOGIN_NOT_REQUIRED` 之类设置项（框架不存在）；权限码判定不进中间件 |
| 越权语义 | 不变：已登录但无权限码 → `require_perm` 302 回工作台（不是 403），本版不碰 |

## 四、实现清单（逐文件、逐函数；确认后按此顺序小步改）

1. **`plugin_host/settings.py`（`MIDDLEWARE` 列表）**：在 `django.contrib.auth.middleware.AuthenticationMiddleware` 与 `django.contrib.middleware.MessageMiddleware` 之间插入 `'django.contrib.auth.middleware.LoginRequiredMiddleware'`，并加中文注释说明「默认拦截 + 白名单」与 `LOGIN_URL` 的关系。
2. **`plugins/auth/views.py`**：新增 `login_not_required` 导入；`login_view` / `logout_view` / `password_reset_notice` 三个函数加 `@login_not_required`（放在各自装饰器链最外层；`login_view`/`logout_view` 目前无其它装饰器）。
3. **`plugins/sso/views.py`**：`sso_login_view` 与 `sso_entry` 各加 `@login_not_required`（`sso_login_view` 已有 `@ensure_csrf_cookie`，白名单放其上方）。
4. **`plugins/language/views.py`**：`language_switch` 加 `@login_not_required`，放在 `@require_POST` 之上。
5. **`plugin_host/middleware.py`**：模块 docstring 追加一段职责划分（三行）：
   - `LoginRequiredMiddleware`（框架）只管「登没登录」，匿名请求在 `process_view` 阶段被拦，与插件无关；
   - `require_perm`（插件视图装饰器）只管「有没有权限码」，在登录之后判定，越权回工作台；
   - 本文件三个容器中间件只管语言默认值 / 主题 / 插件启停路由，都不做身份或权限判定。
6. **`plugin_host/tests_login_guard.py`（新增）**：见 §五。

## 五、测试计划（新增文件，只增不减，不新增 skip、不放宽断言）

| # | 用例 | 断言要点 |
|---|---|---|
| 1 | `test_anonymous_protected_page_redirects_with_next` | 匿名 GET `/plugins/approval/` → 302，`Location` 同时含 `/plugins/auth/login/` 与 `next=%2Fplugins%2Fapproval%2F`（URL 编码后） |
| 2 | `test_anonymous_login_page_ok` | 匿名 GET `/plugins/auth/login/` → 200（不是无限重定向） |
| 3 | `test_anonymous_language_switch_sets_cookie` | 匿名 POST `/plugins/language/switch/`（`lang=en`，带 `next=/plugins/auth/login/`）→ 302 到该 next，`Set-Cookie` 里 `django_language`/`LANGUAGE_COOKIE_NAME`=en，且 `Location` **不含**登录地址 |
| 4 | `test_anonymous_sso_entries_not_blocked` | 匿名 GET `/plugins/sso/` 与 `/plugins/sso/login/` → 都不是跳登录页（200）；后者带 `?ticket=bad` 也仍是 200（页面内报错） |
| 5 | `test_authenticated_same_page_ok` | 已登录（有 `approval_view`）GET `/plugins/approval/` → 200；已登录但无权限的用户 → 302 回 `/`（权限语义未被中间件改写） |
| 6 | `test_guard_sets_are_pinned`（两条集合护栏，一个用例） | ① 静态：枚举非 admin 的 49 条路由，取「**完全没有** `user_passes_test` 族装饰器」的 URL 字符串集合，断言**集合相等**于写死的 7 条（6 白名单 + `theme/switch/`）；② 运行时：逐条匿名 GET（`<converter:name>` 段替换成假值 1），把「不是跳 `LOGIN_URL`」的路由收成集合，断言**集合相等**于 6 条白名单，并断言其余全部 302 到 `LOGIN_URL`。两条互补：静态抓「新增裸奔 / 白名单被套守卫」，运行时抓「白名单被摘掉」。用集合而非数量：数量相等会在「新增一条裸奔 + 误删一条白名单」时相互抵消 |
| 7 | `test_middleware_config_position` | `settings.MIDDLEWARE` 存在 `LoginRequiredMiddleware`，下标大于 `AuthenticationMiddleware`、小于 `MessageMiddleware`；`LOGIN_URL` 非空 |
| 8 | `test_admin_login_exempt_admin_index_blocked`（只做行为断言） | 匿名 GET `/admin/login/` → **200**（不是 302 到我们的登录页）；匿名 GET `/admin/` → 302 且 `Location` 指向 **admin 自己的**登录页（`/admin/login/`）。**不断言 `admin.site.login.login_required is False`**——那是 Django 内部实现属性，升级换豁免机制会假红 |
| 9 | `test_login_round_trip_returns_to_original_page`（收尾修复） | 匿名 GET `/plugins/approval/?x=1&y=2` → 登录页 `next` 带查询串 → POST 登录 → 302 到**带查询串的原页**且随后可 200；登录页 HTML 必须含 `name="next"`；已登录打开登录页 + next 也回 next |
| 10 | `test_external_next_rejected`（收尾修复，auth 插件） | `next=https://evil.example.com/steal` → 登录成功仍 302 到 `/`，`Location` 不含外站域名 |
| 11 | `test_protocol_relative_next_rejected`（收尾修复，auth 插件） | `next=//evil.example.com/steal`（开放重定向最常见绕过形式）→ 302 到 `/`，不跳外站 |

> 说明：第 8 条依赖 `django.contrib.admin` 已安装（本项目已装，`DEBUG=True` 下 `/admin/` 可达）。若你希望测试与 admin 解耦，可去掉第 8 条，代价是 admin 回归靠手工冒烟。

## 六、验收方案（逐条贴证据）

1. **门禁三条**：`manage.py check` / `ruff check .` / `manage.py test --noinput` 全绿；测试数 **357 → 368**（+8 主任务 + 3 收尾修复）。
2. **手工冒烟**（容器 3 worker）：登录后点退出 → 直接访问 `/plugins/attendance/` → 跳登录页且 `next` 指向考勤；登录页切中英 → Cookie 生效、页面语言变化、不跳登录；登录后回工作台正常。
3. **`next` 回跳**：匿名访问 `/plugins/attendance/?x=1` → 登录页 URL 带 `next=/plugins/attendance/%3Fx%3D1`（`redirect_to_login` 用 `QueryDict.urlencode(safe="/")`，斜杠不编码、查询串编码）；提交正确账号密码 → 落到 `/plugins/attendance/?x=1`。
4. **白名单反向验证**：临时去掉 `language_switch` 的 `@login_not_required` → 登录页切语言应失效（302 回登录页），恢复后正常；这条用来证明测试 6 真能兜住「少一个白名单」。
5. **可插拔自检**：停用 `language` 插件 → 顶栏切换入口消失、页面照常；停用 `sso` 插件 → 登录页 SSO 按钮消失；两者停用后匿名访问登录页仍 200。

## 七、不做 / 已知边界

- 不引入任何第三方登录守卫库；不写设置项式白名单；不把权限码判定塞进中间件。
- 不删除既有的 43 处装饰器，也不改 `require_perm` 的越权语义（302 回工作台）。
- **auth 插件停用时**：`LOGIN_URL` 指向的登录视图不存在，匿名访问受保护页会 302 到一个 404 登录地址（与装饰器时代相同，本版不改变）；停用 auth 场景本就只面向已登录会话。
- `theme_switch` 保持受保护（登录后才可用）；若将来登录页要放换肤按钮，需同时补 `@login_not_required`，否则按钮静默失效。

## 八、验收记录（2026-11-10 实测）

### 1. 门禁三条

```
venv\Scripts\python.exe manage.py check          -> System check identified no issues (0 silenced).
venv\Scripts\ruff.exe check .                    -> All checks passed!
venv\Scripts\python.exe manage.py test --noinput -> Ran 368 tests ... OK      （357 → 368，+11）
```

> 测试入口说明（与 v1.7.3 相同）：本机受限令牌下 `tempfile.mkdtemp()` 的 0o700 目录不可写，
> `plugins/approval/tests_v155.py` 的 3 处附件用例会因环境报 `PermissionError`（8 个 error，与本版无关）；
> 用 `venv/run_tests_shim.py` 跑同一套 368 项：**OK**。测试代码零改动、未加 skip、未放宽断言。

### 2. 手工冒烟（先本地，再 3 worker 容器）

容器启动日志：`[entrypoint] migrate → createcachetable → collectstatic`，gunicorn 26.2.0 起 3 个 worker。
中间件位置实测：`Authentication=8 → LoginRequired=9 → Message=10`。

| 匿名访问 | 实测 | 期望 |
|---|---|---|
| `/plugins/auth/login/` | 200 | 允许 |
| `/plugins/auth/logout/` | 302 → `/` | 允许 |
| `/plugins/auth/password-reset/` | 200 | 允许 |
| `/plugins/language/switch/`（GET） | 405（仅 POST） | 允许 |
| `/plugins/sso/login/` | 200（含 `name="ticket"`） | 允许 |
| `/plugins/sso/` | 200 | 允许 |
| `/plugins/attendance/` | 302 → `/plugins/auth/login/?next=/plugins/attendance/` | 必须拦 |
| `/plugins/approval/` | 302 → `/plugins/auth/login/?next=/plugins/approval/` | 必须拦 |
| `/theme/switch/` | 302 → `/plugins/auth/login/?next=/theme/switch/` | 必须拦（不白名单） |
| `/admin/login/` | 200 | admin 登录页放行 |
| `/admin/` | 302 → `/admin/login/?next=/admin/` | 拦，但跳 admin 自己的登录页 |

登录页语言切换（匿名，带 CSRF）：`POST /plugins/language/switch/ lang=en` → 302 到
`/plugins/auth/login/`，`Set-Cookie` 含 `django_language=en` —— 没有被中间件踢回登录页。

登录后：`/` 200、`/plugins/attendance/` 200、`/plugins/approval/` 200。

### 3. `next` 带回与回跳（首次验收只成立一半 → 已在收尾提交修复）

- **带回成立**：匿名 `GET /plugins/attendance/?x=1&y=2` →
  `302 Location: /plugins/auth/login/?next=/plugins/attendance/%3Fx%3D1%26y%3D2`（斜杠不编码，查询串编码）。
- **SSO 通道回跳成立**：`GET /plugins/sso/login/?ticket=<有效>&next=/plugins/attendance/` → 302 `/plugins/attendance/`。
- **账号密码通道回跳不成立**：`POST /plugins/auth/login/` 成功后 `Location: /` —— `login_view` 成功分支是
  `return redirect('index')`，且 `login.html` 表单没有 `next` 隐藏域（实测表单只有 csrf/username/password）。
- 结论：首次验收时验收 3 **只能算「带回成立、回跳对账号密码通道不成立」**。这是 v1.7.0 起的既有行为，
  本版没有引入；随后按「本版把暴露面放大（42 条 URL 全部开始带 next）+ 系统内 SSO 通道已能回跳造成不一致」
  判定为收尾范围，用 `fix(auth)` 提交修复，详见下面第 6 小节。

### 3.1 收尾修复：登录后回跳原页（`fix(auth)`）

修复 7 处：`url_has_allowed_host_and_scheme` 导入、`_next_target()`、`_redirect_after_login()`、
成功分支、已登录访问登录页分支、`render` 上下文补 `next`、两套主题 `login.html` 补隐藏域。
新增 3 条用例（§五 第 9–11 条），测试数 365 → 368。重建容器后真实 HTTP 实测：

| 场景 | 实测 |
|---|---|
| 匿名 `GET /plugins/attendance/?x=1&y=2` | `302 → /plugins/auth/login/?next=/plugins/attendance/%3Fx%3D1%26y%3D2`，解析回原值一致 |
| 登录表单隐藏域 | `next='/plugins/attendance/?x=1&amp;y=2'`（HTML 转义） |
| `POST /plugins/auth/login/` 带 next | `302 → /plugins/attendance/?x=1&y=2`；同一会话再 GET 该 URL → 200 |
| 已登录打开登录页 + next | `302 → next`（不再被扔回首页） |
| `next=https://evil.example.com/steal` | `302 → /`，`Location` 不含外站域名 |
| `next=//evil.example.com/steal` | `302 → /`（协议相对绕过被拒） |

> **两个坑，写在这里免得后人重踩**：
> 1. 只改视图不改 `render` 上下文时，`{{ next }}` 渲染为空串、隐藏域形同虚设——已写进代码注释，
>    并靠 `test_login_round_trip_returns_to_original_page` 的 `assertContains(page, 'name="next"')` 兜住。
> 2. 登录页上有**两个** `name="next"`：语言切换表单带的是当前页 `request.get_full_path`（切完语言留在登录页），
>    登录表单带的才是回跳目标。冒烟脚本按 `name="next"` 取第一个会读到语言表单那个，得出错误结论——
>    验证时必须按所属 `<form action>` 取。

### 4. 护栏反向验证（证明测试 6 真能兜住「少一个白名单」）

临时去掉 `language_switch` 的 `@login_not_required` 后跑 `plugin_host.tests_login_guard`：

```
FAIL: test_anonymous_language_switch_sets_cookie
AssertionError: '/plugins/auth/login/?next=/plugins/language/switch/' != '/plugins/auth/login/'
FAIL: test_guard_sets_are_pinned
AssertionError: Items in the second set but not the first: 'plugins/language/switch/'
Ran 8 tests -> FAILED (failures=2)
```

恢复后与备份 md5 一致，8 条重新全绿。说明「白名单被摘掉」会同时被行为测试与集合护栏抓住。

### 5. 装饰器与部署产物

- 既有 43 处装饰器一处未删（`git diff` 只新增 `@login_not_required` 6 处）。
- 部署产物与工作区一致（重建镜像后 md5 逐一比对）：`plugin_host/settings.py`、
  `plugin_host/middleware.py`、`plugin_host/tests_login_guard.py`、`plugins/auth/views.py`、
  `plugins/sso/views.py`、`plugins/language/views.py` 全部一致。

## 九、待办观察（不在本版修）

1. ✅ **账号密码登录不消费 `next`（本版验收暴露，已在收尾 `fix(auth)` 提交修复）**：原实现成功分支是
   `return redirect('index')`、`login.html` 也没有 `next` 隐藏域，中间件带回的 `next` 被丢弃。修复共 7 处：
   `url_has_allowed_host_and_scheme` 导入 + `_next_target()` + `_redirect_after_login()` 两个小函数 +
   成功分支与「已登录访问登录页」分支改调 `_redirect_after_login()` + `render` 上下文补 `next` +
   两套主题 `login.html` 各补一个隐藏域（`{{ next }}` 取不到值就等于白做，这步不能省）。
   校验口径与 Django `LoginView` 的 `SuccessURLAllowedHostsMixin` 一致，3 条用例见 §五 第 9–11 条。
   SSO 通道已有同类实现（`_safe_next`）可直接复用口径。
2. **admin 子页面跳转不一致（本版实测发现）**：`AdminSite.get_urls().wrap()` 会给站点级页面设置 `wrapper.login_url = reverse('admin:login')`，所以 `/admin/`、`/admin/jsi18n/` 匿名访问跳 **admin 自己的**登录页；而 ModelAdmin 页面（如 `/admin/user/user/`）没有该属性，中间件按 `settings.LOGIN_URL` 跳**我们的**登录页。非 staff 用户从 OA 登录页进 admin 会再被 `admin_view` 甩到 admin 登录页（多一跳，不阻断）。是否统一留给后续版本，本版只按负责人裁定断言 `/admin/` 的行为。
3. **roadmap 顺延**：v1.7.4 改为本项后，「认证后端插件化 + 限流计数原子化 P2」顺延为 **v1.7.5**（P2 仍排第一项），需同步 roadmap 的版本表与差距矩阵，并写明让位原因（沿用 v1.7.1/v1.7.2 让位先例）。
4. **越权统一 403 还是 302**：本版沿用「302 回工作台」，与 v1.5.4 起的口径一致；若将来要区分「未登录」与「无权限」，属于语义变更，单独立项。
5. **中间件与 `MessageMiddleware` 的相对位置**：本版按官方顺序放在 `AuthenticationMiddleware` 后、`MessageMiddleware` 前；目前无功能依赖，若将来中间件要在登录跳转时塞 message，需要重新评估。
6. **匿名可达面盘点机制**：本版用两条集合护栏（静态 + 运行时）兜住；若插件数量继续增长，可考虑在 `manage.py check` 里加一条系统检查（v1.9 插件契约补全时一起做）。
