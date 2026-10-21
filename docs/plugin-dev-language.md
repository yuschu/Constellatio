# 插件开发文档：language（语言切换插件，默认中英文）

> 关联插件：themes.risograph（外壳）、各业务插件（菜单/文案国际化）
> 版本规划：v1.3 · 文档版本：draft-01 · 2026-10-21
> 状态：**待确认后开发**

## 一、需求

新增语言切换插件：默认**中文**，支持**中英文切换**；顶栏提供切换入口，选择即时生效（session 级，不要求持久化到用户表）。

## 二、设计要点

| 项 | 决策 |
|---|---|
| 形态 | 新插件 `plugins/language`（切换能力本身插件化） |
| 机制 | Django i18n：`LocaleMiddleware` + `gettext_lazy`；切换写 `request.session['django_language']` |
| 默认语言 | `zh-hans`（settings.LANGUAGE_CODE 不变） |
| 翻译载体 | 项目根 `locale/en/LC_MESSAGES/django.po`（手工维护 gettext 源）+ **纯 Python 小脚本编译 .mo**（无 gettext 二进制依赖，跨平台 Windows 可用） |
| 覆盖范围 | v1.3 先覆盖：外壳导航（工作台/功能/登录/登出/欢迎语）、各插件菜单 label、各插件核心页标题与主按钮；**不做全站逐字翻译**（文档声明范围） |
| 菜单国际化 | `PluginMeta.menus` 的 label 改 `gettext_lazy`（容器聚合时保持 lazy，模板渲染时自动翻译） |
| 页面 | base.html 顶栏加语言切换（POST 表单 + CSRF）；`LANGUAGE_CODE` 注入模板供高亮当前语言 |

## 三、接口 / 路由

| 路由 | 视图 | 说明 |
|---|---|---|
| `/plugins/language/switch/` | language_switch（POST） | 参数 `lang` ∈ {`zh-hans`, `en`}；写 session → redirect 回来源页（`request.META.HTTP_REFERER` 或 `index`） |

## 四、国际化接入步骤

1. `plugin_host/settings.py`：
   - MIDDLEWARE 在 `CommonMiddleware` 之后加 `django.middleware.locale.LocaleMiddleware`
   - `LOCALE_PATHS = [BASE_DIR / 'locale']`
2. base.html 顶栏加语言切换块（POST 表单，CSRF token，两个按钮"中文 / EN"）
3. 外壳文案与各插件菜单 label、页面标题改用 `{% trans %}` / `gettext_lazy`
4. `locale/en/LC_MESSAGES/django.po` 维护 msgid/msgstr；`tools/compile_mo.py`（纯 Python .mo 编译器）生成 `django.mo`
5. 新增文案流程：改源码 → 更新 .po → 重编译 .mo（写进开发指南/迭代规范）

## 五、权限

- 语言切换对**所有登录用户**开放（无权限码）；无需上链（非审计性操作，符合现有上链只录关键操作的原则）

## 六、验收标准

1. 默认中文；切 EN 后外壳导航、插件菜单、核心页面标题/按钮变英文，立即生效（同会话）
2. 切回中文恢复
3. 语言选择不丢失登录态；未登录访问登录页也可切换（登录页含切换入口）
4. 无 gettext 二进制环境下 .mo 可正常编译（纯 Python 脚本）
5. 既有功能全部不受影响（回归冒烟）

## 七、测试计划

- 单测：language_switch 视图（合法/非法 lang、session 写入、redirect）
- 冒烟：登录 → 切 EN → 各插件页标题/菜单为英文 → 切回中文 → 回归 6 插件页 200

## 八、改动文件清单

| 文件 | 动作 |
|---|---|
| `plugins/language/`（apps/views/urls/templates） | 新增 |
| `plugin_host/settings.py` | LocaleMiddleware + LOCALE_PATHS + OA_PLUGINS 增 language |
| `plugin_host/registry.py` | menus label 支持 gettext_lazy（聚合不强制 str） |
| `themes/risograph/templates/base.html` | 顶栏语言切换块 + 外壳文案 trans |
| 各插件 apps.py（menus label）+ 页面模板标题/按钮 | gettext_lazy / {% trans %} |
| `locale/en/LC_MESSAGES/django.po` + `tools/compile_mo.py` | 新增翻译文件与编译脚本 |
| `.gitignore` / 文档 | 无 .mo 入库策略（构建时编译）或入库均可（文档定：**.mo 不入库，部署时用脚本编译**） |
