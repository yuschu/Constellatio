# 插件开发文档：v1.5.7 插件主权（语言插件化 + 可停用 + 开关 UI）

> 关联插件：plugin_host（注册表 / 中间件 / 上下文处理器）、language、workspace、auth、user、structure、themes
> 版本：v1.5.7 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（153 项测试全绿 + Docker 重建 + HTTP / CLI 冒烟）

## 一、需求

1. **中英文切换插件升级为语言插件**，不再是系统必需：不可停用清单里移除 language；停用后**继续使用最后设置的语言**，只是不再显示切换入口。
2. **认证、用户与组织可停用**：`auth` / `user` / `structure` 移出禁停清单，可由管理员在插件开关页停用。
3. 插件开关页的**停用/启用按钮改成开关**（toggle switch），切换即生效。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 插件改名 | `language` 插件的展示名由「中英文切换」改为「语言」（`PluginMeta.title`），能力不变：默认中文 + 中英切换 |
| 语言默认值 | 无有效 Cookie 时固定 `LANGUAGE_CODE`（中文），不跟随浏览器 `Accept-Language` |
| 语言中间件归属 | `DefaultLanguageMiddleware` 从 `plugins/language/middleware.py` **迁到 `plugin_host/middleware.py`**（容器级），语言插件停用/卸载后仍生效 |
| 最后设置的语言 | 切换写**持久 Cookie** `django_language`（`LANGUAGE_COOKIE_AGE`，默认 1 年）；插件停用后 Cookie 继续生效，即「沿用最后设置的语言」；无 Cookie 回默认中文 |
| 切换入口 | 顶栏与登录页的语言表单仅在 `language` 插件启用时渲染（上下文处理器注入 `plugins_enabled`），停用后无 404 死表单 |
| 禁停清单 | 收敛为 **`workspace` 唯一**（关掉它等于关掉开关入口）；`auth / user / structure / language` 均可运行时停用 |
| 停用风险提示 | 开关页对 `auth / user / structure` 显示风险说明；`auth` 停用=登录/登出入口关闭（已登录会话仍可用） |
| 防锁死兜底 | 新增管理命令 `manage.py plugin_switch list / on <key> / off <key>`，不依赖 HTTP，可在停用 auth 后恢复 |
| 开关 UI | Bootstrap 5 `form-check form-switch`（两套主题共用，无新增主题 CSS）；勾选变化即提交表单（外部 JS 监听 `change`，不新增内联 `onclick`） |
| 数据 | **不新增表、无迁移**；开关仍用 `workspace_pluginswitch`，语言偏好走 Cookie |
| 静态停用边界 | `OA_PLUGINS enabled=False` 的静态停用仍需重启（v1.10 处理），本版只保证运行时开关 |

## 三、实现

### 3.1 容器层

- `plugin_host/middleware.py`：新增 `DefaultLanguageMiddleware`（Cookie → `LANGUAGE_CODE`），设置 `MIDDLEWARE` 指向它；删除 `plugins/language/middleware.py`。
- `plugin_host/registry.py`：`get_menus(user, plugins=None)` 支持复用一次 `get_enabled_plugins()` 结果，避免每个请求两次查开关表。
- `plugin_host/context_processors.py`：注入 `plugins_enabled`（本次请求实际启用的插件名集合），供外壳按插件启停隐藏入口。

### 3.2 language 插件

- `apps.py`：`title=_('语言')`，`version='1.5.7'`；仍无模型、无权限码、无菜单。
- `views.py`：切换写 `max_age=settings.LANGUAGE_COOKIE_AGE` 的持久 Cookie（`samesite='Lax'`），其余（`next` 校验、POST only、非法语言不写）不变。

### 3.3 workspace 插件

- `PROTECTED = {'workspace'}`；`CRITICAL_WARNINGS` 为 `auth / user / structure` 提供停用风险文案（`gettext_lazy`）。
- 开关页：每行一个 `role="switch"` 复选框；受保护插件渲染为禁用开关 + 「系统必需」；未受保护插件切换即提交。
- 新增 `management/commands/plugin_switch.py`：
  - `list`：打印全部注册插件与静态/DB 生效状态；
  - `on <key>` / `off <key>`：写 `PluginSwitch` 并发 `plugin_toggled`（可恢复被停用的 auth）。
  - 命令**不受禁停清单限制**，作为兜底通道。

### 3.4 外壳

- `themes/*/templates/base.html`：语言表单包 `{% if 'language' in plugins_enabled %}`；登录/登出链接包 `{% if 'auth' in plugins_enabled %}`。
- `themes/*/templates/login.html`：语言表单同样按 `language` 启停渲染。
- 两套主题改动一致（`r-*` 契约不变，不新增主题 CSS）。

## 四、路由与权限

| 路由 / 命令 | 权限 | 变化 |
|---|---|---|
| `/plugins/workspace/` | `workspace_manage` | 开关 UI；风险提示 |
| `/plugins/workspace/<app_key>/toggle/` | `workspace_manage` | 除 `workspace` 外全部可切换 |
| `/plugins/language/switch/` | 无（全员） | 写持久 Cookie；插件停用后路由 404 |
| `manage.py plugin_switch` | 服务器命令行 | 新增兜底通道 |

## 五、测试计划

1. 语言：中间件迁到 `plugin_host` 后默认中文/ Cookie 生效/ 非法值回退不变；Cookie 为持久 Cookie；停用 language 后首页仍英文、顶栏无切换表单、开关页可停用。
2. 禁停清单：仅 `workspace` 受保护；`auth / user / structure / language` 可停用并写 DB；`auth` 停用后登录页 404、已登录会话工作台仍 200。
3. 开关 UI：开关页渲染 `role="switch"`；受保护插件为禁用开关 + 「系统必需」；仍保留表单 POST 语义（`enabled=1`）。
4. 管理命令：`plugin_switch off auth` 写库并可通过 `on auth` 恢复；`list` 输出含状态。
5. 回归：既有 144 项测试不回归；双语文案。

## 六、改动文件

| 文件 | 动作 |
|---|---|
| `plugin_host/middleware.py` / `settings.py` | 语言中间件迁入容器；`MIDDLEWARE` 改指向 |
| `plugin_host/registry.py` / `context_processors.py` | `get_menus` 复用启用列表；注入 `plugins_enabled` |
| `plugins/language/`（apps / views / middleware 删除） | 改名语言插件；持久 Cookie |
| `plugins/workspace/`（views / template / 命令） | 禁停收敛、风险提示、开关 UI、兜底命令 |
| `themes/*/templates/base.html` `login.html` | 语言 / 认证入口按插件启停隐藏 |
| `plugins/*/tests.py` | 更新与新增单测 |
| `locale/en/LC_MESSAGES/django.po` | 新增文案 |
| `docs/roadmap.md`、`docs/plugin-dev-language.md`、`docs/plugin-dev-workspace.md`、`README.md`、快照 | 同步 |

## 七、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **153 项通过**（基线 144 + 新增 9） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 开关 UI 冒烟 | 开关页 200，含 `role="switch"` / `data-plugin-switch` /「系统必需」/ auth 风险提示 |
| 语言停用冒烟 | 先切英文 → 停用 language：首页仍英文、无切换入口、`/plugins/language/switch/` 404；恢复后入口回归 |
| 插件停用冒烟 | 停用 notice：路由 404、工作台菜单与公告简报入口收敛；恢复后 200 |
| CLI 冒烟（容器内） | `plugin_switch list` 输出 9 个插件；`off auth` 后登录页 404；`on auth` 后恢复 200 |

> 冒烟脚本为临时文件，已删除；演示账号与 v1.5.6 一致。
