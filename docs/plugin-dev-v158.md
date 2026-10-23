# 插件开发文档：v1.5.8 功能区主题切换（运行时换肤）

> 关联：plugin_host（theming / middleware / 视图 / 上下文处理器）、themes/*、全部业务模板
> 版本：v1.5.8 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（158 项测试全绿 + Docker 重建 + 双主题冒烟）

## 一、需求

把**主题切换**加到**功能区**（侧栏「功能」区）：用户不离开页面即可在「Corporate Clean / Risograph」之间切换，选中即生效，刷新/下次访问保持。

> 与 v1.5 的差异：v1.5 定稿「改 `OA_THEME` + 重启生效，不做运行时热切换」。本版按负责人要求升级为**运行时切换**，`OA_THEME` 退化为默认/回退主题。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 入口 | 侧栏「功能」区底部新增「主题」按钮组（两个主题各一个 `r-lang` 风格按钮），当前主题高亮 |
| 存储 | Cookie `oa_theme`（持久 1 年，`samesite='Lax'`）；不新增表、无迁移；不写用户表 |
| 默认/回退 | 无 Cookie 或 Cookie 值非法 → `settings.OA_THEME`（默认 `corporate-clean`）；启动仍校验 `OA_THEME` 合法 |
| 生效机制 | `ThemeMiddleware` 每请求读 Cookie → contextvar；`ThemeLoader` 按当前主题解析模板目录；插件模板未命中主题时回退 app 模板 |
| 模板加载 | `APP_DIRS=False` + 显式 `loaders`（`ThemeLoader` → `app_directories`）；**不使用 cached loader**（模板按请求主题变化，缓存会串主题） |
| 静态资源 | 两套主题的 `static` 都进 `STATICFILES_DIRS`（路径按 `themes/<key>/` 隔离）；`collectstatic` 一次收集两套 |
| 路由 | `POST /theme/switch/`（容器路由，非插件）；`next` 经 `url_has_allowed_host_and_scheme` 校验，非法主题不改 Cookie |
| 权限 | 登录用户即可（显示偏好，无权限码、不上链） |
| 边界 | 只切换主题模板（base / home / login）与主题 CSS；插件业务模板共用；`r-*` 契约不变；不做主题级权限、不做 per-user DB 偏好 |

## 三、实现

### 3.1 容器

- `plugin_host/theming.py`：`discover_themes` 加进程内缓存；新增 `THEME_COOKIE_NAME` / `resolve_theme_key` / `current_theme_key`（contextvar）/ `ThemeLoader(FileSystemLoader)`（`get_dirs()` 返回当前主题 templates）。
- `plugin_host/middleware.py`：新增 `ThemeMiddleware`（Cookie → contextvar → `request.theme`，响应后复位）。
- `plugin_host/context_processors.py`：新增 `themes` 处理器（可选主题列表 + `current_theme`）。
- `plugin_host/views.py`：`theme_switch`（POST only，写 Cookie 后 302）。
- `plugin_host/urls.py`：`path('theme/switch/', ...)`。
- `plugin_host/settings.py`：`THEME_COOKIE_AGE=1 年`；TEMPLATES loaders；`STATICFILES_DIRS` 收全部主题静态；MIDDLEWARE 增 `ThemeMiddleware`。

### 3.2 主题

- `themes/*/templates/base.html`：功能区底部新增主题按钮组（POST `theme=<key>`），不新增主题 CSS。

## 四、测试计划

1. 默认主题：无 Cookie → corporate-clean 模板与 CSS；
2. Cookie 切换：`oa_theme=risograph` → 渲染 risograph 的 base/home 与 CSS，且不出现 corporate CSS；
3. 切换视图：POST 写持久 Cookie（`max_age=THEME_COOKIE_AGE`）并 302 回 `next`；
4. 非法主题：不改 Cookie；Cookie 非法值回退默认主题；
5. 安全：GET 405；外部 `next` 被拦回 `/`；
6. 功能区入口：首页含 `/theme/switch/` 与两个主题名；
7. 静态查找：两套主题 CSS 都可 `finders.find`；
8. 回归：既有 153 项不回归；双语页面。

## 五、改动文件

| 文件 | 动作 |
|---|---|
| `plugin_host/theming.py` | 缓存、Cookie 常量、contextvar、`ThemeLoader` |
| `plugin_host/middleware.py` | `ThemeMiddleware` |
| `plugin_host/settings.py` | loaders / 静态目录 / 中间件 / Cookie 时长 |
| `plugin_host/context_processors.py` | `themes` 处理器 |
| `plugin_host/views.py` / `urls.py` | `theme_switch` 视图与路由 |
| `themes/*/templates/base.html` | 功能区主题按钮组 |
| `plugin_host/tests.py` | 新增 5 项运行时切换测试 |
| `locale/en/LC_MESSAGES/django.po` | 「主题」文案 |
| `docs/plugin-dev-theme.md` / `docs/roadmap.md` / `README.md` / 快照 | 同步 |

## 六、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **158 项通过**（基线 153 + 新增 5） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 双主题冒烟 | 默认 corporate → POST 切 risograph：首页 / 公告页 / 开关页全部换肤，corporate CSS 不再出现；`/static/themes/risograph/css/risograph.css` 200 |
| 回退与安全 | 非法主题保持原主题；切回 corporate 正常；GET 405、外部 `next` 回 `/`（单测覆盖） |

> 冒烟脚本为临时文件，已删除；主题偏好是 Cookie（1 年），不影响其他浏览器会话。
