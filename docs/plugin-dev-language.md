# 插件开发文档：language（语言切换插件，默认中英文）

> 关联插件：plugin_host 容器（中间件 / 注册表）、themes.risograph（外壳）、各业务插件（菜单 / 页标题）
> 版本规划：v1.4 · 文档版本：draft-04（已实现）· 2026-10-22
> 状态：**✅ 已实现并跑通**（13 项单测全绿 + 中英双语 13 页 HTTP 冒烟；全量 51 项测试通过）

## 〇、draft-02 复核结论（先看这节）

draft-01 写于 v1.3 之前，有 4 处与当前 Django 5.2 / 代码现状不一致；本版已修正，并补了 2 个遗漏：

| # | draft-01 写法 | 复核结果 | draft-02 决策 |
|---|---|---|---|
| 1 | 切换写 `request.session['django_language']` | Django 5.2 已移除 `LANGUAGE_SESSION_KEY`；`LocaleMiddleware` 只读 Cookie（`settings.LANGUAGE_COOKIE_NAME`，默认 `django_language`） | 改为**会话级 Cookie**；不写 session、不落用户表 |
| 2 | 直接用 `django.middleware.locale.LocaleMiddleware` | 无 Cookie 时会先跟随 `Accept-Language`；英文浏览器首次访问不是中文，违背「默认中文」 | 用插件自带 `DefaultLanguageMiddleware`（继承 LocaleMiddleware）：Cookie 有效则用，否则固定 `LANGUAGE_CODE` |
| 3 | 覆盖范围写「v1.3 先覆盖」 | 笔误；v1.3 是 structure，language 是 v1.4 | 全文改 v1.4 |
| 4 | `.mo` 不入库、部署时编译，但没写编译入口 | 容器与本地都没有编译步骤，英文会静默回退中文 | 新增 `tools/compile_mo.py`，写入 `entrypoint.sh` 与测试前置步骤 |

另补两处 draft-01 未覆盖的细节：

- 切换是 POST，`next` 必须用 `url_has_allowed_host_and_scheme` 校验，避免开放重定向。
- `language` 是外壳级能力，建议加入 workspace 禁停清单，避免停用后顶栏留下 404 死表单（见「待确认项」）。

## 一、需求

在最小可行闭环（v0.1–v1.3）之上新增语言切换插件：默认**中文**，支持**中英文切换**；顶栏提供切换入口，选择即时生效；不持久化到用户表；不引入 gettext 二进制依赖（Windows 本地可直接跑）。

## 二、设计要点

| 项 | 决策 |
|---|---|
| 形态 | 新插件 `plugins/language`，切换能力本身插件化；无模型、无迁移、无侧栏菜单 |
| 默认语言 | `settings.LANGUAGE_CODE = 'zh-hans'` 不变；无有效 Cookie 时固定中文，不跟随浏览器 `Accept-Language` |
| 可选语言 | `settings.LANGUAGES = [('zh-hans', '简体中文'), ('en', 'English')]` |
| 存储 | 会话级 Cookie `django_language`（`LANGUAGE_COOKIE_AGE=None`），浏览器关闭即回默认；不写 session、不落用户表 |
| 生效机制 | `DefaultLanguageMiddleware` 读 Cookie → `translation.activate()`；下一次请求即生效，无需重启 |
| 翻译机制 | Django i18n：源码中文为 msgid，`locale/en/LC_MESSAGES/django.po` 提供英文；`zh-hans` 直接回退 msgid |
| 编译 | `tools/compile_mo.py` 纯 Python 生成 `.mo`；`.mo` 不入库；`entrypoint.sh` 启动时编译 |
| 菜单国际化 | `PluginMeta.menus` 的 label 改 `gettext_lazy`；模板渲染时按当前语言求值 |
| 覆盖范围 | 外壳 + 12 个菜单 + 页标题 + 主按钮 + 登录错误；不做全站逐字翻译（明细见第六节） |
| 权限 | 所有用户（含未登录的登录页）；无权限码 |
| 上链 | 不上链（个人显示偏好，非审计事件）；不发信号 |

## 三、数据模型 / 权限 / 信号

- **数据模型：无。** `plugins/language` 不建表、不生成迁移。
- **权限码：无。** `PluginMeta.permissions=[]`；语言切换对所有用户开放。
- **信号 / 上链：无。** 切换语言是显示偏好，不进入 SHA-256 留痕链；如后续需要审计，再加 `language_switched` 信号。

## 四、接口 / 路由

| 路由 | 视图 | 说明 |
|---|---|---|
| `/plugins/language/switch/` | `language_switch` | POST only；`lang` ∈ {`zh-hans`, `en`}，`next` 可选；写 Cookie 后 302 回 `next` → Referer → `/`；GET 返回 405 |

无列表页、无侧栏入口；切换按钮直接渲染在 `base.html` 顶栏与 `login.html`。

## 五、实现方案

### 5.1 settings.py

```python
INSTALLED_APPS += ['plugins.language']

MIDDLEWARE = [
    ...
    'django.contrib.sessions.middleware.SessionMiddleware',
    'plugins.language.middleware.DefaultLanguageMiddleware',   # 替换 stock LocaleMiddleware
    'django.middleware.common.CommonMiddleware',
    ...
]

LANGUAGES = [('zh-hans', '简体中文'), ('en', 'English')]
LOCALE_PATHS = [BASE_DIR / 'locale']

OA_PLUGINS += [{'app': 'plugins.language', 'enabled': True}]
```

注意：**替换** stock `LocaleMiddleware`，不要两套同时挂载；位置在 Session 之后、Common 之前。

### 5.2 中间件（plugins/language/middleware.py）

```python
from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class DefaultLanguageMiddleware(LocaleMiddleware):
    """默认中文：Cookie 有效则用 Cookie，否则固定 LANGUAGE_CODE；不跟随 Accept-Language。"""

    def process_request(self, request):
        valid = {code for code, _ in settings.LANGUAGES}
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang not in valid:
            lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
```

保留父类 `process_response`（Content-Language / Vary 头）。

### 5.3 切换视图（plugins/language/views.py）

```python
from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@require_POST
def language_switch(request):
    lang = request.POST.get('lang')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        next_url = '/'
    response = redirect(next_url)
    if lang in {code for code, _ in settings.LANGUAGES}:
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang)   # max_age=None → 会话 Cookie
    return response
```

### 5.4 插件注册（plugins/language/apps.py）

```python
register(PluginMeta(
    name='language', version='1.4.0',
    menus=[], permissions=[],
    urls='plugins.language.urls', signals=[], templates=None, app=self,
))
```

### 5.5 模板

- `base.html`：`{% load i18n %}` + `{% get_current_language as LANGUAGE_CODE %}`；顶栏加切换表单（`next={{ request.get_full_path }}`、两个 submit 按钮、当前语言高亮）。
- `login.html`：同样加切换表单，保证未登录也能切换。
- 各业务模板：`{% load i18n %}`，对 `{% block title %}`、`<h2>`、主按钮使用 `{% trans %}`。
- 菜单：8 个 `apps.py` 的 label 改 `gettext_lazy`（**不能**用 `gettext`，否则启动时冻结语言）。
- 动态标题：`plugins/user/views.py` 的「新建用户 / 编辑用户 / 新建角色 / 编辑角色」用 `gettext` 生成。
- `risograph.css`：新增 `.r-lang` / `.r-lang.is-active` 样式。

### 5.6 翻译文件与编译

```
locale/en/LC_MESSAGES/django.po      # 手工维护，msgid=中文，msgstr=英文
tools/compile_mo.py                  # 纯 Python .po → .mo（无 gettext 依赖）
```

`compile_mo.py` 要求：支持注释、多行字符串、`\n` / `\"` / `\\` 转义、fuzzy 跳过；遇到 `msgid_plural` 直接报错（v1.4 不用复数）；无 `.po` 时正常退出；生成标准 `.mo`（magic `0x950412de`）。

- `entrypoint.sh`：在 `migrate` 前执行 `python tools/compile_mo.py`。
- `.gitignore`：新增 `*.mo`。
- 本地流程：改 `.po` → `python tools/compile_mo.py` → `runserver` / `test`。
- 缺少 `.mo` 时英文会静默回退中文，不算崩溃，但验收不通过。

## 六、覆盖范围（v1.4 精确边界）

| 文件 | 覆盖内容 |
|---|---|
| `themes/risograph/templates/base.html` | 功能 / 暂无可用功能 / 登录 / 登出 / 页脚；顶栏语言切换 |
| `themes/risograph/templates/login.html` | 标题、副标题、用户名、密码、登录按钮、错误提示 |
| `themes/risograph/templates/home.html` | 工作台、欢迎语、4 张卡片标题与描述 |
| 8 个 `plugins/*/apps.py` | 12 个菜单 label（工作台 / 部门 / 用户 / 角色 / 审批中心 / 待我审批 / 公告中心 / 考勤打卡 / 留痕链 / 插件开关 / 组织架构 / 应用结构） |
| `plugins/approval/templates`（4 个） | 页标题、h2、发起审批、提交审批、通过、驳回、会签通过、会签驳回、去审批 |
| `plugins/notice/templates`（3 个） | 公告中心、发布公告、发布 |
| `plugins/attendance/templates`（1 个） | 考勤打卡、签到、签退 |
| `plugins/blockchain/templates`（1 个） | 操作留痕链 |
| `plugins/workspace/templates`（1 个） | 插件开关、启用、停用 |
| `plugins/structure/templates`（1 个） | 组织架构、应用模板 |
| `plugins/user/templates`（5 个） | 部门 / 用户 / 角色管理、新建 / 保存 / 修改 / 启用 / 解冻 / 禁用 / 冻结权限、动态表单标题 |
| `plugins/auth/views.py` | 用户名或密码错误 |
| `plugins/user/views.py` | 动态 title 的 4 个字符串 |

**明确不做**：表头 / 字段标签 / 空状态说明、表格内的业务数据、JS `confirm()` 文案、Django Admin、表单校验消息、日志与异常文案。未覆盖区域保持中文，属文档声明的范围，不算缺陷。

## 七、测试计划

### 7.1 单元测试（`plugins/language/tests.py`）

1. 无 Cookie + `Accept-Language: en-US` → `get_language() == 'zh-hans'`
2. Cookie `django_language=en` → `get_language() == 'en'`
3. POST `lang=en` → 302，`Set-Cookie` 无 `Max-Age` / `Expires`（会话 Cookie）
4. POST `lang=fr` → 302，但不写 Cookie
5. GET `/plugins/language/switch/` → 405
6. `next=https://evil.example` → 302 到 `/`
7. `next=/plugins/notice/` → 302 到该路径
8. 匿名 POST 可用（不要求登录）
9. `translation.override('en')` 后 `str(gettext_lazy('工作台')) == 'Workspace'`
10. 编译器：临时 `.po`（多行 / 转义 / fuzzy）→ `.mo` → `gettext.GNUTranslations` 读取正确

> 9 / 10 依赖已编译的 `.mo`：`setUpClass` 调 `tools.compile_mo.compile_all()`，或测试前手工执行。

### 7.2 HTTP 冒烟

1. `python tools/compile_mo.py` → `runserver` → 登录
2. 切 EN → 侧栏菜单、页标题、主按钮变英文 → 切回中文
3. 登出到登录页 → 切 EN → 登录 → 仍为英文
4. 6 个插件页均 200；留痕链校验通过
5. Docker：`docker compose up -d --build` → entrypoint 编译 → 同样验证
6. 可插拔自检：停用 language（若允许）→ 顶栏无死表单、其余功能正常

## 八、验收标准

1. 首次访问（即使浏览器是英文）默认中文
2. 切 EN 后外壳、菜单、页标题、主按钮立即变英文，无需重新登录
3. 切回中文恢复；语言选择是会话 Cookie，关浏览器回中文
4. 登录页可切换，未登录也可用
5. 第六节列出的范围全部生效；未覆盖区域保持中文且有文档说明
6. `manage.py test` 全绿（新增 ≥10 项）
7. 容器内 entrypoint 自动编译，无 gettext 二进制依赖
8. 既有 38 项测试与 6 个插件页回归通过；可插拔自检通过

## 九、改动文件清单

| 文件 | 动作 |
|---|---|
| `plugins/language/`（`__init__` / `apps` / `urls` / `views` / `middleware` / `tests`） | 新增 |
| `plugin_host/settings.py` | 中间件、LANGUAGES、LOCALE_PATHS、INSTALLED_APPS、OA_PLUGINS |
| `tools/compile_mo.py` | 新增（纯 Python .mo 编译器） |
| `locale/en/LC_MESSAGES/django.po` | 新增（英文 catalog） |
| `themes/risograph/templates/base.html` / `login.html` / `home.html` | 切换入口 + 文案 |
| `themes/risograph/static/themes/risograph/css/risograph.css` | `.r-lang` 样式 |
| 8 个 `plugins/*/apps.py` | 菜单 label 改 `gettext_lazy` |
| 16 个业务模板 | 页标题 / h2 / 主按钮 `{% trans %}` |
| `plugins/auth/views.py` / `plugins/user/views.py` | 运行时 `gettext` 文案 |
| `plugins/workspace/views.py` | 禁停清单加 `language`（待确认） |
| `entrypoint.sh` / `.gitignore` | 编译步骤 / 忽略 `*.mo` |
| 文档（实现后同步） | README、project-overview、constraints、ai-assisted、development-guide、database-design（标注无表）、本文件完成态 |

## 十、风险与回退

| 风险 | 处置 |
|---|---|
| 菜单用了 `gettext` 而非 `gettext_lazy` | 启动时语言被冻结；code review 强制检查 8 个 `apps.py` |
| 中间件顺序错误 / 两套 LocaleMiddleware 并存 | 固定「Session 之后、Common 之前」；settings 只留一套 |
| `.mo` 未编译 | 英文回退中文；entrypoint / 测试前置编译，冒烟必查 |
| 开放重定向 | `url_has_allowed_host_and_scheme` + 单测覆盖 |
| 静态停用 language 但顶栏仍渲染 | 回退时同步移除 base/login 切换块；或保持插件常启用 |
| 部分翻译看起来「半中半英」 | 第六节明确边界；后续 v1.5 可扩到表头 / 字段 |
| 删除插件后 middlewares 指向不存在模块 | 回退清单必须同时删 `DefaultLanguageMiddleware` |

**回退**：移除 `OA_PLUGINS` / `INSTALLED_APPS` 条目与中间件 → 还原 base/login/home 与菜单 label → 删除 `plugins/language` / `locale` / `tools` → 无数据库迁移，回退干净。

## 十一、确认记录（2026-10-22）

负责人确认，5 项**全部按推荐执行**：

1. `language` **加入 workspace 禁停清单**（外壳级能力）。
2. **默认中文，忽略浏览器 `Accept-Language`**。
3. 语言选择用**会话 Cookie**（关浏览器恢复中文），不写入用户表。
4. 覆盖范围按第六节；表头 / 字段 / JS confirm 暂不翻译。
5. `.mo` **不入库**，由 entrypoint 与测试前编译。

版本顺序：v1.4 language 先做，基础设施补齐（v1.5–v1.8）后置；路线见 `docs/roadmap.md`。

## 十二、实现记录（2026-10-22）

- 插件：`plugins/language/`（apps / urls / views / middleware / tests）
- 中间件：`DefaultLanguageMiddleware`（Cookie 优先，否则 `zh-hans`；不跟随 `Accept-Language`）
- 配置：`settings.LANGUAGES` / `LOCALE_PATHS` / MIDDLEWARE / INSTALLED_APPS / OA_PLUGINS
- 翻译：`locale/en/LC_MESSAGES/django.po`（72 条在用）+ `tools/compile_mo.py`
- 模板：`base.html` / `login.html` / `home.html` + 8 个 `apps.py` 菜单 + 16 个业务模板的标题 / h2 / 主按钮
- 禁停：`workspace.PROTECTED` 增加 `language`
- 测试：`plugins/language/tests.py` 13 项；全量 **51 项全绿**
- 冒烟：中文 / 英文各 13 个页面 200；登录页可切换；语言 Cookie 为会话级；`.mo` 不入库
