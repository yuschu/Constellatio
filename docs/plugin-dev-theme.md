# 插件开发文档：theme（主题插件化 + Corporate Clean 默认主题）

> 关联：plugin_host 配置 / themes / 全部业务模板（UI 组件契约）
> 版本规划：v1.5 · 文档版本：draft-01 · 2026-10-22
> 状态：**✅ 已实现并跑通**（2026-10-22；63 项测试全绿 + 默认/备选主题冒烟）

## 〇、确认记录（2026-10-22）

负责人确认：

1. v1.5 **冻结保留** r-* / --r-* 契约；
2. corporate-clean 作为默认，risograph 保留为备选；
3. --r-pink 在 Corporate Clean 中映射为品牌蓝，历史变量名不改；
4. hero **照抄 Prompt 的 gray-900**（已知对比度不足，记录为已知例外）；
5. 登录页增加 SSO / 忘记密码等未实现入口（占位/禁用，不伪造登录）；
6. 改配置/环境变量 + 重启生效，不做运行时热切换；**重启后的首屏加载动画必须实现**。

## 一、背景与目标

v1.4 已把 language 插件跑通，下一步按 roadmap 做「基础设施 Provider 契约 + 主题插件化」。

当前现状：

- 主题只有 themes/risograph，以 Django app 形式挂在 INSTALLED_APPS；
- OA_THEME 只是 settings 里的一个字符串，**代码没有读取它**；
- base.html / login.html 硬编码 themes/risograph/css/risograph.css；
- 业务模板大量使用 r-* 类与 --r-* 变量，实际与 Risograph 视觉强耦合。

v1.5 目标：

1. **主题即插件**：新建 themes/<key>/ + theme.json + 改 OA_THEME（重启）即切换，不需要改 Python 注册表。
2. **新增 Corporate Clean 主题并设为默认**：按 Prompt/corporate-clean-hard-prompt.md 的企业简洁风实现。
3. **保留 Risograph 作为第二主题**：证明切换真实可回退，而不是删掉旧主题。
4. **不引入 Tailwind / 新前端框架 / 新依赖**：把 Tailwind token 映射为 CSS 变量 + Bootstrap 5 栅格。
5. 主题切换只影响模板与静态资源，不碰数据库、不产生迁移。

## 二、设计决策

| 项 | 决策 |
|---|---|
| 主题形态 | themes/<key>/ 目录 + theme.json 清单；**不再要求是 Django app** |
| 发现 | 启动时扫描 themes/*/theme.json，生成 ThemeMeta；找不到或字段缺失即启动失败 |
| 选择 | OA_THEME（默认 corporate-clean，可用环境变量覆盖）；**改配置 + 重启生效** |
| 模板 | TEMPLATES[0]['DIRS'] = [active_theme/templates]；主题可覆盖任意 app 模板（DIRS 优先于 APP_DIRS） |
| 静态 | STATICFILES_DIRS = [active_theme/static]；collectstatic 只收当前主题 |
| 旧 app | 从 INSTALLED_APPS 移除 themes.risograph；themes/risograph/apps.py 保留但不加载 |
| 组件契约 | **v1.5 冻结现有 r-* 类与 --r-* 变量为主题无关契约**；两套主题都必须实现（详见第四节） |
| 默认主题 | corporate-clean |
| 备选主题 | risograph（视觉保持现状） |
| 依赖 | 不新增 Python / 前端依赖；继续用 Bootstrap 5 CDN + 主题 CSS |
| 登录入口 | Corporate Clean / Risograph 登录页都加 SSO（禁用占位）与忘记密码（占位页）；不做真实认证 |
| 加载动画 | 首屏 `.r-loader`；刷新 / 重启恢复后的第一次加载显示；服务器宕机期间浏览器只能显示连接错误 |

### 2.1 为什么保留 r-* 前缀（而不是现在改名 ui-*）

- 16 个业务模板、base/login/home 共 19 个模板大量使用 r-card / r-btn / r-table / --r-ink 等；改名是纯机械但会扩大 v1.5 的回归面。
- 主题可插拔的关键是「插件只依赖稳定的组件契约，不依赖某个主题的视觉」，而不是前缀叫什么。
- v1.5 把 r-* **文档化为通用 UI 契约**，两套主题各自实现；v1.6 如需要再统一重命名为 ui-*，插件代码可无感迁移。

> 该契约已确认冻结；若后续要改名 ui-*，另开迭代处理，避免与主题切换混在一起。

## 三、目录结构与清单

~~~
themes/
├── corporate-clean/          # v1.5 新增，默认主题（目录名带连字符，不作 Python 包）
│   ├── theme.json
│   ├── templates/
│   │   ├── base.html
│   │   ├── home.html
│   │   └── login.html
│   └── static/themes/corporate-clean/css/corporate-clean.css
└── risograph/                # 现有主题，保持视觉
    ├── theme.json            # v1.5 新增
    ├── apps.py               # 保留但不加载
    ├── templates/...
    └── static/themes/risograph/css/risograph.css
~~~

theme.json 示例：

~~~json
{
  "name": "Corporate Clean",
  "version": "1.0.0",
  "description": "企业简洁风：蓝灰配色、圆角卡片、轻阴影、200ms 以内交互",
  "templates": "templates",
  "static": "static"
}
~~~

校验规则：

- name / version 必填；
- templates 目录必须存在且有 base.html；
- static 目录必须存在；
- key = 目录名；重复 / 非法 JSON / 缺字段 → 启动时抛 ImproperlyConfigured，并列出可用主题。

## 四、主题契约（两套主题都必须满足）

### 4.1 页面文件

| 文件 | 说明 |
|---|---|
| templates/base.html | 全局外壳；必须提供 block content，保留语言切换、登录/登出、侧栏菜单 |
| templates/home.html | 工作台；必须 extends base.html |
| templates/login.html | 登录页；独立页面，保留语言切换与 CSRF |

主题可以额外覆盖任意 app 模板（如 approval/approval_list.html），但不要求。

### 4.2 UI 组件类（v1.5 冻结）

业务模板只允许依赖下列类；主题必须为它们提供视觉：

| 类 | 用途 |
|---|---|
| .r-btn / .r-btn--blue / .r-btn--plain | 主按钮 / 蓝色按钮 / 次按钮 |
| .r-card | 卡片容器 |
| .r-input / .r-select / .r-textarea | 表单控件 |
| .r-table | 数据表格（含 th / td / 行 hover） |
| .r-badge + .r-badge--blue/pink/green/orange | 状态标签 |
| .r-nav | 顶栏 |
| .r-offset-hover | 文字/链接 hover 反馈 |
| .r-register-mark | 装饰角标；Corporate Clean 中隐藏 |
| .r-grain / .r-halftone | 纹理；Corporate Clean 中关闭 |
| .r-lang / .r-lang.is-active | 语言切换按钮 |
| .r-loader / .r-loader__spinner / .r-loader__text / .is-hidden | 首屏加载动画（两套主题都要实现） |
| .r-shadow-sm/md/lg/blue/orange | 少量模板内联使用的阴影工具类 |
| .r-bg-* / .r-text-* | 少量工具类 |

### 4.3 CSS 变量（v1.5 冻结）

模板内联样式与主题 CSS 使用：

--r-paper、--r-paper-2、--r-ink、--r-pink、--r-blue、--r-orange、--r-green、--r-font、--r-radius、--r-ease、--r-dur、--r-shadow-sm/md/lg/blue/orange

Corporate Clean 中这些变量**保留原名但映射为企业色**（--r-pink 映射为品牌蓝，历史命名不改），避免改 19 个模板的内联 var(--r-shadow-orange)。

## 五、接入代码（实现时改动）

### 5.1 plugin_host/theming.py（新增）

~~~python
import json
from dataclasses import dataclass
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class ThemeMeta:
    key: str
    name: str
    version: str
    root: Path
    templates: Path
    static: Path


def discover_themes(base_dir: Path) -> dict[str, ThemeMeta]:
    themes = {}
    for manifest in sorted((base_dir / 'themes').glob('*/theme.json')):
        key = manifest.parent.name
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImproperlyConfigured(f'主题清单无法解析: {manifest}: {exc}') from exc
        for field in ('name', 'version', 'templates', 'static'):
            if not data.get(field):
                raise ImproperlyConfigured(f'主题 {key} 缺少字段: {field}')
        root = manifest.parent
        templates = (root / data['templates']).resolve()
        static = (root / data['static']).resolve()
        if not (templates / 'base.html').is_file():
            raise ImproperlyConfigured(f'主题 {key} 缺少 templates/base.html')
        if not static.is_dir():
            raise ImproperlyConfigured(f'主题 {key} 缺少 static 目录')
        themes[key] = ThemeMeta(key, data['name'], data['version'], root, templates, static)
    return themes


def get_theme(base_dir: Path, key: str) -> ThemeMeta:
    themes = discover_themes(base_dir)
    if key not in themes:
        available = ', '.join(sorted(themes)) or '(none)'
        raise ImproperlyConfigured(f'未知主题 OA_THEME={key!r}；可用: {available}')
    return themes[key]
~~~

### 5.2 settings.py

~~~python
# 移除 'themes.risograph'（主题不再依赖 INSTALLED_APPS）
OA_THEME = os.environ.get('OA_THEME', 'corporate-clean')

from plugin_host.theming import get_theme
_theme = get_theme(BASE_DIR, OA_THEME)
TEMPLATES[0]['DIRS'] = [str(_theme.templates)]
STATICFILES_DIRS = [str(_theme.static)]
~~~

注意：TEMPLATES 必须先于这段定义；STATICFILES_DIRS 只放当前主题，避免两套主题 CSS 同时进入静态目录。

> ThemeMeta 是 v1.5 的 provider 元信息；v1.6 的 chart / auth 复用同样的 key / name / version / templates / static 模型，必要时再抽公共 ProviderMeta。

### 5.3 Docker

docker-compose.yml 的 web 环境增加：

~~~yaml
OA_THEME: ${OA_THEME:-corporate-clean}
~~~

entrypoint.sh 已有 collectstatic，会按当前主题收集；切换主题 = 改 env / settings + 重启容器。

## 六、Corporate Clean 风格规范（按 Prompt 映射）

> Prompt 是 Tailwind 语法；本项目不引 Tailwind，下列 token 全部落到 CSS 变量与选择器。

### 6.1 色板

| 角色 | 值 | 用途 |
|---|---|---|
| 页面背景 | #f8fafc (slate-50) | body |
| 卡片 | #ffffff | .r-card |
| 主色 | #2563eb (blue-600) | 主按钮、链接、焦点环 |
| 主色 hover | #1d4ed8 (blue-700) | 按钮 hover |
| 浅主色 | #eff6ff (blue-50) | 选中、浅背景 |
| 主文字 | #111827 (gray-900) | 标题 |
| 次文字 | #4b5563 (gray-600) | 正文 |
| 弱文字 | #6b7280 (gray-500) | 辅助 |
| 边框 | #e5e7eb (gray-200) | 卡片/表格 |
| 控件边框 | #d1d5db (gray-300) | 输入框 |
| 成功 | #16a34a | 徽标 |
| 警告 | #d97706 | 徽标 |
| 错误 | #dc2626 | 徽标 / 危险按钮 |

### 6.2 排版

- 字体：-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif；正文不用等宽。
- 标题：font-weight 600; letter-spacing -0.01em; text-transform none（覆盖 Risograph 的全大写）。
- 正文：15px / 1.6；辅助 13px。
- 正文行宽尽量 65–75 字符；表格/表单不受此限。

### 6.3 圆角 / 阴影 / 间距

| 项 | 值 |
|---|---|
| 按钮 / 输入 / 徽标 | 8px（rounded-lg） |
| 卡片 | 12px（rounded-xl） |
| 卡片内边距 | 24px（p-6） |
| 卡片阴影 | 0 1px 2px rgba(15,23,42,.06)（shadow-sm） |
| 卡片 hover | 0 4px 12px rgba(15,23,42,.10)（shadow-md） |
| 元素间距 | 16px / 24px（gap-4 / gap-6） |
| 页面区块 | 48–80px（py-12 / py-16） |

### 6.4 交互

- 按钮：transition 150ms ease-out；hover 上浮 -2px + shadow-md；active scale(.98) + 阴影回 sm。
- 卡片：transition 200ms ease-out；hover 上浮 -2px + shadow-md。
- 焦点：box-shadow 0 0 0 2px #fff, 0 0 0 4px rgba(37,99,235,.45) + outline none；**ring-offset 2px**。
- 图标容器：hover 蓝底 + 白色图标 + scale(1.1)（首页/侧栏可选）。
- 所有过渡 ≤ 200ms；prefers-reduced-motion 下关闭位移/缩放。

### 6.5 组件映射

| 现有类 | Corporate Clean 表现 |
|---|---|
| .r-btn | 蓝底白字、8px 圆角、shadow-sm、hover 上浮/变蓝-700、active 缩放 |
| .r-btn--plain | 白底、gray-300 边框、gray-700 文字 |
| .r-card | 白底、gray-200 边框、12px 圆角、shadow-sm；hover 上浮 |
| .r-input | 白底、gray-300 边框、8px 圆角、focus 蓝环 + offset |
| .r-table | 无粗边框；表头 gray-50、gray-500 文字；行 hover gray-50；底线 gray-200 |
| .r-badge | 浅色底 + 深色字 + 细边框；蓝色/绿色/橙色/红色四种 |
| .r-nav | 白底、底部灰线；链接 gray-600，hover 蓝-600 |
| .r-offset-hover | 颜色变蓝 + 轻微上移；不使用套印阴影 |
| .r-register-mark / .r-grain / .r-halftone | display: none（企业简洁风不用装饰纹理） |
| --r-pink | 映射为品牌蓝（历史变量名，语义按组件理解） |
| --r-shadow-orange/blue | 映射为细阴影（内联危险按钮不再有彩色套印） |

### 6.6 页面设计

- **base.html**：白色顶部导航（品牌蓝方块 + Constellatio + 语言切换 + 用户/登出）；slate-50 页面底；白色侧栏卡片（菜单）；内容区；slate-50 页脚。移动端侧栏堆叠到顶部。
- **home.html**：蓝色 hero + **gray-900 文字**（按负责人要求照抄 Prompt；WCAG 对比度不足，记录为例外）+ 4 张白色卡片（插件架构 / 主题 / 已启用插件 / 插件开关），卡片 hover 上浮。
- **login.html**：slate-50 居中；白色 12px 圆角卡片；品牌标识；用户名/密码；蓝色按钮；语言切换；下方增加：
  - “企业 SSO 登录（即将上线）”按钮：`type=button disabled aria-disabled=true title=暂未接入`；
  - “忘记密码？”链接 → `/plugins/auth/password-reset/` 占位页（提示联系管理员，不发送邮件、不伪造重置成功）。
- 两套主题的登录页都加这两个入口，行为一致，视觉各自适配。
- 不嵌套卡片；不做渐变；不做单侧粗边框。

### 6.7 首屏加载动画（重启/刷新）

> 服务器真正重启期间，页面无法由服务端渲染；浏览器会显示连接错误。这里实现的是**服务恢复后第一次页面加载**的加载动画，以及站内跳转时的短暂 loading。

- 两套主题的 base.html / login.html 顶部加：

~~~html
<div class="r-loader" id="page-loader" role="status" aria-live="polite">
  <span class="r-loader__spinner" aria-hidden="true"></span>
  <span class="r-loader__text">加载中…</span>
</div>
<noscript><style>.r-loader{display:none}</style></noscript>
~~~

- CSS：固定全屏、主题背景色、居中 spinner + 文案；`.is-hidden` 时 opacity 0 / visibility hidden，200ms 过渡。
- JS：window load 后加 `.is-hidden`；`beforeunload` 时移除 `.is-hidden`（站内跳转短暂显示）；2.5s 兜底隐藏，避免资源失败时卡住。
- prefers-reduced-motion：停掉 spinner 旋转，仅保留静态标识。
- 文案“加载中…”进 `locale/en/LC_MESSAGES/django.po`（Loading…）。

## 七、Risograph 迁移

1. 新增 themes/risograph/theme.json；
2. 从 INSTALLED_APPS 移除 themes.risograph；
3. themes/risograph/apps.py 保留但不加载（不再提供 label / AppConfig 能力）；
4. themes/risograph/templates/base.html / login.html 继续引用自己的 themes/risograph/css/risograph.css；
5. Risograph CSS 补齐第四节契约（目前基本都有；补 .r-lang 已有、.r-btn--plain 等检查）；
6. Risograph 主体视觉不变；登录页增加与 Corporate Clean 一致的 SSO/忘记密码占位入口与首屏 loader，行为一致。
7. Risograph 的 `login.html` / `base.html` 也要加 `.r-loader` 与入口；样式用 Risograph 自己的 token。

## 八、切换与部署流程

1. 改 OA_THEME='risograph'（settings 或环境变量）；
2. 本地：重启 runserver；
3. 容器：docker compose up -d --build（entrypoint 会 collectstatic 当前主题）；
4. 验收：登录页/工作台 CSS 链接与视觉切换；业务页仍可访问。

## 九、测试计划

### 9.1 单元测试（plugin_host/tests.py）

1. discover_themes 能发现 corporate-clean 与 risograph；
2. 默认 settings.OA_THEME == 'corporate-clean'；
3. TEMPLATES[0]['DIRS'][0] 指向当前主题 templates；
4. STATICFILES_DIRS[0] 指向当前主题 static；
5. get_theme(BASE_DIR, 'missing') 抛 ImproperlyConfigured 并列出可用主题；
6. 两套主题都有 theme.json / base.html / home.html / login.html / CSS；
7. get_template('base.html').origin.name 落在当前主题目录；
8. finders.find('themes/corporate-clean/css/corporate-clean.css') 非空；
9. Corporate Clean CSS 包含契约选择器 .r-btn / .r-card / .r-input / .r-table / .r-badge / .r-nav 与 --r-ink；
10. 非法清单（缺字段 / 坏 JSON / 缺 base.html）启动即报错；
11. 两套主题登录页都含 SSO（disabled）与忘记密码链接；
12. `/plugins/auth/password-reset/` 返回 200 且含“暂未开放”提示；
13. base.html / login.html 含 `.r-loader` 标记；CSS 含 `.r-loader` / `.r-loader__spinner`。

### 9.2 HTTP 冒烟

1. 默认主题：登录页/工作台/6 个插件页 200，CSS 链接指向 corporate-clean；
2. OA_THEME=risograph 子进程/容器：同样页面 200，CSS 指向 risograph；
3. 切换语言后主题不丢（language Cookie 与主题互不影响）；
4. collectstatic 后 CSS 200；
5. 可插拔自检：新增第三个最小主题（只放 base/home/login + CSS）→ 改 OA_THEME → 能启动；删除该目录后改回默认 → 正常；
6. 登录页 SSO 按钮 disabled；忘记密码进入占位页 200；
7. loader 标记存在，JS 有 load / beforeunload / 2.5s 兜底；
8. OA_THEME=risograph 登录页同样有入口与 loader。

## 十、验收标准

1. 默认打开工作台是 Corporate Clean：白卡片、蓝主按钮、slate-50 背景、8/12px 圆角、细阴影、系统字体。
2. OA_THEME=risograph + 重启 + collectstatic 后，视觉与 v1.4 的 Risograph 一致。
3. 主题切换不改数据库、不产生迁移；业务功能、权限、语言切换全部不受影响。
4. 两套主题都实现第四节契约；插件模板无需按主题分支。
5. 焦点环、reduced-motion 符合第六节；无 rounded-none / 渐变 / 彩色套印；hero 的 gray-900 对比度为例外（按负责人要求）。
6. 全量 63 项测试全绿（既有 51 + 主题/登录/loader 等 12）；中英双语冒烟通过。
7. 无 Tailwind / 新前端依赖 / 新 Python 依赖。
8. Docker 一键部署后默认主题生效，切主题后重建容器生效。
9. 登录页可见 SSO（禁用）/ 忘记密码入口；忘记密码进入占位页；不伪造登录/重置成功。
10. 重启后首次加载与站内跳转显示 `.r-loader`，2.5s 兜底隐藏；reduced-motion 下不旋转。

## 十一、改动文件清单

| 文件 | 动作 |
|---|---|
| plugin_host/theming.py | 新增：清单发现 / 校验 / ThemeMeta |
| plugin_host/settings.py | 新增 OA_THEME 解析、TEMPLATES.DIRS、STATICFILES_DIRS；移除 themes.risograph |
| plugin_host/tests.py | 新增：主题发现 / 默认 / 非法 / 模板与静态解析 |
| themes/corporate-clean/ | 新增：theme.json + base/home/login + CSS |
| themes/risograph/templates/base.html / login.html | 加 `.r-loader` 与 SSO/忘记密码入口 |
| plugins/auth/urls.py / views.py | 新增 `/plugins/auth/password-reset/` 占位页 |
| plugins/auth/templates/auth/password_reset_notice.html | 新增占位页 |
| locale/en/LC_MESSAGES/django.po | 增加“加载中…” |
| themes/risograph/theme.json | 新增 |
| themes/risograph/apps.py | 保留、不再加载（文档标注） |
| docker-compose.yml | 增加 OA_THEME 环境变量 |
| README.md / docs/tech-stack-and-architecture.md / docs/development-guide.md / docs/project-overview.md / docs/roadmap.md | 实现后同步 |
| docs/plugin-dev-theme.md | 本文件，完成态 |

## 十二、风险与回退

| 风险 | 处置 |
|---|---|
| 业务模板有未覆盖的 r-* 类 → 新主题缺样式 | 第四节冻结契约 + 测试检查关键选择器 + 全页冒烟 |
| 内联 var(--r-*) 变量缺失 | Corporate CSS 定义全部 --r-* 兼容变量 |
| 两套主题 CSS 同时进入静态目录导致串味 | 只把当前主题放进 STATICFILES_DIRS |
| 切主题忘记 collectstatic | entrypoint 每次启动 collect，文档写明 |
| 主题通过 APP_DIRS 回退到旧主题 | 主题不再进 INSTALLED_APPS；DIRS 只含当前主题 |
| 删除当前主题导致启动失败 | get_theme 启动即报错并列可用主题；不会静默回退 |
| 视觉回归（业务页） | 逐页冒烟 + 对比截图（登录/工作台/审批/用户/公告/考勤/留痕/开关/结构） |
| hero gray-900 对比度不足 | 负责人已确认照抄 Prompt，记录为例外；若后续要 WCAG 再改白字 |
| 占位入口被误解为可用功能 | SSO 用 disabled + “即将上线”；忘记密码进入明确的“暂未开放”占位页 |
| loader 因资源失败卡住 | 2.5s 兜底隐藏；noscript 直接隐藏；reduced-motion 停旋转 |

**回退**：OA_THEME='risograph' + 重启 + collectstatic 即回到 v1.4 视觉；代码层可删 themes/corporate-clean 与 theming 接入（无迁移）。

## 十三、确认结果（2026-10-22）

1. v1.5 **冻结保留** r-* / --r-* 契约；
2. corporate-clean 默认，risograph 备选；
3. --r-pink 映射品牌蓝，历史变量名不改；
4. hero **照抄 Prompt 的 gray-900**（已知对比度不足，记录为例外）；
5. 登录页增加 SSO / 忘记密码入口；SSO 禁用占位，忘记密码进占位页，不伪造登录/重置；
6. 改配置/环境变量 + 重启生效；重启恢复后的首屏加载动画必须实现（服务器宕机期间浏览器只能显示连接错误）。

## 十四、实施顺序（确认后）

1. 写 plugin_host/theming.py + settings 接入 + 主题测试（先让 risograph 通过）；
2. 给 risograph 补 theme.json，迁移出 INSTALLED_APPS；
3. 新建 corporate-clean（theme.json + base/home/login + CSS），设为默认；
4. 加 SSO/忘记密码占位入口（两套登录页）+ password-reset 占位页；
5. 加 `.r-loader`（两套 base/login）+ 文案 + 兜底逻辑；
6. 逐页冒烟 + 修 r-* 漏样式；
7. 全量测试 + 双语冒烟 + Docker 冒烟；
8. 文档同步 + tag v1.5.0 + push。

## 十五、实现记录（2026-10-22）

- 主题发现：`plugin_host/theming.py` 扫描 `themes/*/theme.json`，当前主题写入 `TEMPLATES[0]['DIRS']` / `STATICFILES_DIRS`；未知主题启动即报错。
- 默认主题：`OA_THEME=corporate-clean`；`OA_THEME=risograph` 可切回备选。`themes.risograph` 已从 `INSTALLED_APPS` 移除。
- Corporate Clean：`themes/corporate-clean/`（theme.json + base/home/login + CSS），`--r-*` 全部保留并映射企业色；`--r-pink` = 品牌蓝。
- Risograph：补 `theme.json` 并保留 CSS；base/login 加 loader 与 SSO/忘记密码占位入口。
- 登录占位：SSO 按钮 `disabled` + “即将上线”；忘记密码 → `/plugins/auth/password-reset/`，仅提示联系管理员。
- 首屏 loader：两套 base/login 都有 `.r-loader`；load 后隐藏、beforeunload 显示、2.5s 兜底、noscript 隐藏、reduced-motion 停旋转。
- 测试：63 项全绿；`collectstatic` 128 个文件；`OA_THEME=risograph` 登录页/占位页/工作台冒烟通过。
- Docker：`docker compose up -d --build` 成功；entrypoint compile/migrate/collectstatic/gunicorn 3 workers 正常；默认 Corporate Clean 登录页/CSS/占位页 200；`OA_THEME=risograph` 重建后 CSS 200，再切回 Corporate Clean。
- 访问：http://localhost:8000 （默认超管 admin / Constellatio@2026，若已改密码以实际为准）。
- 已知例外：hero 按负责人要求使用 gray-900 on blue-600，对比度不足，记录在第十二节。
- 无迁移、无新依赖；`.mo` 仍不入库。
