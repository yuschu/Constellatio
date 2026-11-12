# 前端重构方案（参考 DeepSeek Harness）

> 状态：**草案 v1（2026-11-12），待负责人拍板后执行**。本文只做方案与判据，不含实现代码。
> 依据：`deepseek-ai/deepseek-harness` 的公开结构与文档 + 本项目实测盘点（数字均可复核）。
> 决策记录：负责人已选定「引入组件框架」档位 + 「向 DSH 深色极简靠近」视觉基调；本文在该档位内给出三条可选实现与推荐。

---

## 零、结论先行

1. **DSH 值得抄的不是 React，是三条纪律 + 一个机制**：原子层与插件系统解耦的组件库、结构性组件分层、几何与颜色 token 全覆盖；以及「插件把自己的 UI 片段注册进命名 slot」。
2. **本项目已有 slot 雏形**：Django 的 `{% block %}` + 插件注册表已经能表达"插件贡献 UI"这件事，缺的是**细粒度命名 slot**、**token 覆盖**、**结构组件分层**——这三件都不需要新框架。
3. **CSP 是最硬的约束**：v1.7.16 已把 `script-src` 收紧到 `'self' 'nonce-…'`（无 `'unsafe-inline'`、无 `'unsafe-eval'`）。据此：
   - Alpine.js **标准版直接不可用**（靠 `new Function()`，必须 `unsafe-eval`）；官方 CSP build 可用但只支持"most of"表达式语法，复杂逻辑必须挪进外部 JS，声明式优势打折；
   - HTMX 主体 **CSP 友好**，只需避开 `hx-on:` / `js:` 这类内联表达式写法；
   - React 必须走构建链（产物是外部 `.js`，本身不违规），但与现有 SSR 模板体系冲突最大。
4. **推荐**：`HTMX + 组件 CSS 层（token/原子/结构）+ 模板命名 slot`。这是"引入组件框架"档位内代价最小、且能同时拿到 DSH 的纪律与交互质感的一条路。

---

## 一、现状实测（2026-11-12，可复核）

| 项 | 实测值 |
|---|---|
| 主题 CSS | `corporate-clean.css` **430 行**、`risograph.css` **360 行**（合计 790 行） |
| CSS 变量 | 各 **17 个**（8 色 + 字体 + 圆角 + 缓动/时长 + 5 档阴影） |
| 裸十六进制色值 | corporate-clean **71 处**、risograph **20 处**（合计 **91 处**，是变量数的 5 倍） |
| `!important` | 6 / 2 处 |
| 规则块 | 102 / 71 |
| 模板总数 | **37 个**：`plugins/**` 30 个（**2052 行**）、`themes/*` 6 个（base 89/92、home 17/18、login 74/80）、`plugin_host/` 1 个（home_dashboard 267 行） |
| 插件模板内 `style="…"` | **137 处**（30 个模板内） |
| 自写 JS | 仅 `plugin_host/static/js/confirm.js`（38 行） |
| 前端依赖 | Bootstrap 5（本地 vendor）+ ECharts（图表页），**无构建链、无 npm、无 CI 前端步骤** |
| 主题骨架重复 | 两个 `base.html` 结构重复度约 90%（89 / 92 行） |
| 已有注册点 | `{% block title %}` / `extra_css` / `content` / `extra_js` |

**结论**：前端体量很小（CSS 790 行 + JS 38 行 + 模板 2500 行）。重构的真实工作是**收敛**（91 处裸色值、137 处 style=、两套重复骨架），不是重写。

---

## 二、DSH 可迁移清单（逐条映射到本项目）

| DSH 的做法 | 本项目等价物 | 落点 |
|---|---|---|
| 原子组件库刻意**不依赖**插件系统与 slot | 纯 CSS 组件类（`.r-btn` / `.r-input` / `.r-badge` / `.r-pill` / `.r-field`），零 JS 依赖 | 两个主题 CSS + 新建 `plugin_host/static/css/base.css` |
| 结构性组件层（PageHeader / Toolbar / StatBar / EmptyState / ActionRow / Tabs / Dialog） | 模板 include 片段目录 `templates/includes/ui/` | 新建，37 个模板逐步替换 |
| 颜色 **100% 消费 token** | 消灭 91 处裸色值；结构 token 共用、色彩 token 分套 | 两主题 CSS 首段 `.r-tokens` |
| 几何纪律（控件 32px、工具栏 44–48px） | 固定控件高度/工具栏高度/表格行高，写入 token | 同上 |
| 插件把 UI 片段注册进命名 slot | `{% include %}` + 插件 registry 声明 slot 片段 | `plugin_host/registry` + `base.html` |
| 插件自带客户端代码（`dsh-plugin-*/client.js`） | 插件自带 `static/<plugin>/plugin.js`（非内联） | `plugins/<name>/static/` |
| 插件清单页（官方/已安装分组 + 开关 + 描述 + 图标） | 已有 `/plugins/workspace/`，对齐语义 | `switch_list.html` |
| client / host 分离 | 本项目天然如此（模板 + 视图分离） | 无需改造 |
| Cordis 运行时组合 | **不引入**（Django 无运行时组合器，用注册表 + include 静态组合） | — |

**明确不迁移**：React、Cordis、pnpm monorepo、Node 构建链（除非选路线 C）。

---

## 三、三条路线代价对比（在「引入组件框架」档位内）

| 维度 | 路线 A：HTMX + 组件 CSS + slot | 路线 B：原生 Web Components | 路线 C：React/TS SPA |
|---|---|---|---|
| 新依赖 | HTMX（单文件 vendor，离线可放） | 无 | React + 构建链（npm/pnpm） |
| 与 Django SSR | **完全兼容**，模板继续用 | 兼容，用自定义元素包裹 | **不兼容**，需建 JSON API 层 |
| CSP nonce-only | **合规**（避开 `hx-on:` / `js:`） | **最合规**（外部 .js 注册元素） | 合规（打包产物为外部 .js），但需重做 CSP 白名单 |
| 483 项测试基线 | **全部保留**，`assertContains` 仍有效 | 保留 | **大量作废**（模板断言、`assertTemplateUsed`、`assertContains` 全要重写） |
| 37 个模板 | 增量改造 | 增量改造 | **全部废弃** |
| 两套主题机制 | 保留（token 分套） | 保留 | 需在 React 内重建（CSS vars 或 styled） |
| Docker/CI | 无变化 | 无变化 | 多阶段构建、CI 加 node 步骤 |
| 估算迭代数 | **3–4** | 4–5 | **8–10** |
| 主要风险 | 局部刷新的错误处理与 CSP 细节 | 组件生态薄弱、上手陡 | 回归面失控、CSP 与双主题重做 |

**判定**：路线 A 是"引入组件框架"档位下的最优解；路线 C 若坚持，必须接受测试基线重写——与本项目"测试只增不减、禁止放宽断言"的既定门禁**直接冲突**，需要负责人单独授权破例。

---

## 四、推荐路线（A）的技术组成

### 4.1 四层结构

```
tokens.css        结构 token（尺寸/间距/圆角/字阶/动效）+ 语义 token 契约
  └ base.css      原子组件（btn / input / badge / pill / field / table / link）
      └ ui/       结构组件 include（page-header / toolbar / stat-bar / empty-state / action-row / tabs / dialog）
          └ hx     局部刷新（片段路由返回 HTML 片段，非整页）
```

- **tokens.css**：结构 token 全站唯一（`--r-control-h: 32px`、`--r-toolbar-h: 44px`、`--r-row-h`、`--r-space-*`、`--r-radius-*`、`--r-text-*`）；**色彩 token 由每个主题单独定义**（`--r-bg` / `--r-surface` / `--r-text` / `--r-border` / `--r-accent` / `--r-ok/warn/danger`）。
- **base.css**：原子类只依赖 token，不依赖任何插件或 slot（对应 DSH `primitives` 的"刻意解耦"）。
- **ui/**：结构组件是 Django include，参数走 `{% include ... with %}`；不含业务逻辑。
- **HTMX**：只用于"局部刷新"（列表分页、筛选、图表数据区、通知已读），**不接管导航**。

### 4.2 命名 slot 注册（UI 插件化的落地机制）

slots 定义在 `base.html` 的固定位置，插件通过 registry 贡献片段：

```html
{# themes/<theme>/templates/base.html #}
{% block nav_extra %}{% for tpl in ui_slots.nav_extra %}{% include tpl %}{% endfor %}{% endblock %}
```

- registry 新增 `ui_fragments` 声明：插件在 `plugin.json` / registry 里列出"我往哪个 slot 贡献哪个模板路径"；
- 渲染端只做 `{% for tpl in ui_slots.<slot> %}{% include tpl %}{% endfor %}`，**插件间零直接 import** 的规矩不变；
- 与 Django `{% block %}` 并存：`block` 用于主题/页面覆盖，`slot` 用于**插件横向注册**（两者职责不同，不重复）。

slot 初版清单（6 个，够用且可控）：
`nav_extra`（顶栏右侧）、`sidebar_bottom`（侧栏底部）、`page_header_actions`（页头操作区）、`dashboard_widgets`（工作台卡片区）、`form_footer_extra`（表单页脚）、`detail_sidebar`（详情页右栏）。

### 4.3 与既有权重规矩的兼容

- 插件间零直接 import → slot 通过 registry 间接组合，成立；
- 不引入新运行时依赖 → HTMX 作为本地 vendor 单文件（同 Bootstrap 处理方式），不算 npm 依赖；
- CSP nonce-only → 新增 JS 一律外部 `.js`；禁止 `hx-on:`、`js:` 表达式、内联事件。

---

## 五、设计系统（深色极简）

### 5.1 色彩 token（已实测，详见 `docs/dsh-visual-spec.md`）

2026-11-12 起本地实例（`npx @deepseek-ai/dsh web`）实测，**浅色态已 1:1 拿到**：114 个语义别名全量、四级半透明描边、三阶近黑文字、品牌主色为近黑而非蓝。完整值见 `docs/dsh-visual-spec.md` §3。

**结构照搬**（这是最该抄的部分，不是色值）：

```
--r-static-*   原始色板
--r-alias-*    语义别名（组件只消费这一层，换主题只替换映射）
--r-radius-*   6 档：4 / 8 / 12 / 16 / 20 / 28
```

三项实测确认的质感来源，比配色更能决定观感：

| 项 | 实测值 | 作用 |
|---|---|---|
| 描边四级 | `#0000000a` / `#0000001a` / `#0000001f` / `#00000029` | 同一黑的不同透明度，叠任何底色都自然 |
| 角形状 | `corner-shape: superellipse(1.5)` | 连续曲率替代四分之一圆，消除切线拐点 |
| 发丝线 | `0.8px`（局部 `0.5px`） | 不用 1px，Retina 下更精细 |
| 激活态 | `inset 0 0 0 1px` 内阴影 | 替代 border，避免布局抖动 |

**深色态已补齐（2026-11-12）**：深色 114 个 alias 已全部按 **CSS 原值**实测（`getComputedStyle(body).getPropertyValue()` 直读，非像素采样），完整表在 `docs/dsh-visual-spec.md` §3.5，可直接取用，不需要再补采。

深色有两条与浅色相反的规律，落地时必须记住：

1. **背景分层不能靠色值**：`bg-base #151517` 与 `layer-1 #232324` 只差 **1.16:1**，斑马纹 `#1b1b1c` 只差 **1.06:1**，发丝分隔叠出来 **1.13:1**——全部低于非文本 3:1 阈值，深色下"底色差一档"肉眼看不见。层级必须靠**圆角 + 内边距 + 相对位置**表达，这与浅色（`layer-1/2/3` 全是 `#fff`、靠描边和阴影分层）的机制相反。
2. **状态色不能当底色托字**：error `#f25a5a` 压在 success-tertiary `#233c2c` 上只有 **3.64:1**，business `#7aaaff` 压 business-tertiary `#34415b` 只有 **4.39:1**，都低于 AA 4.5。校验提示要放在 `bg-base`/`layer-1` 上，彩色只用于图标和边框。

对比度全表见 `docs/dsh-visual-spec.md` §11.4（按 WCAG 公式精确计算）。

### 5.2 几何纪律（对齐 DSH 实测值）

| 项 | 值 |
|---|---|
| 控件高度（按钮/输入/选择） | **32px** |
| 工具栏高度 | **44–48px** |
| 表格行高 | 40px（紧凑）/ 48px（常规） |
| 圆角 | 8px（控件 = `radius-sm`）/ 12px（卡片 = `radius-md`） |
| 间距阶 | 4 / 8 / 12 / 16 / 24 / 32 |

### 5.3 组件清单

- **原子（base.css）**：btn（primary/secondary/ghost/danger，3 尺寸）、input/textarea/select、checkbox/radio、badge、pill、field（label+hint+error）、divider、link、spinner、table 基础。
- **结构（ui/ include）**：page-header（标题+面包屑+操作区）、toolbar（筛选+搜索+批量操作）、stat-bar（指标卡横排）、empty-state（插图+文案+主操作）、action-row（行内操作组）、tabs、dialog（确认/表单）、toast。
- 现有 `.r-badge` / `.r-card` / `.r-menu-link` / `.r-lang` 保留类名做兼容迁移，不搞一次性大改名。

### 5.4 两主题策略

- **共用**：结构 token、原子类、结构组件 include、slot 机制。
- **分套**：色彩 token、纹理/装饰（risograph 的 `r-grain`、套印标记）、字体栈。
- **重塑顺序**：先把 corporate-clean 改成深色极简基线，再让 risograph 在同一 token 契约下重排（保留印刷风特征但降低饱和度以融入深色）。

---

## 六、分阶段里程碑

| 阶段 | 交付物 | 验收判据 | 回滚 |
|---|---|---|---|
| **P0 基线冻结** | 重构前全量绿 + 冒烟记录 + 截图存档 | 483 项 OK、CSP 四项冒烟通过、`ruff`/`check` 绿 | — |
| **P1 token 层** | `tokens.css` + 两主题色彩 token 化，消灭 91 处裸色值 | Grep 裸十六进制 = 0（token 定义除外）；视觉零回归（截图比对）；483 项 OK | 单文件回滚 |
| **P2 原子组件** | `base.css` + 原子类，137 处 `style=` 逐页改类 | `style=` 计数逐页下降并记录；每页截图比对；483 项 OK | 按页回滚 |
| **P3 结构组件 + 骨架合并** | `ui/` include 集 + 两个 `base.html` 抽公共骨架 | 两 base 重复度 < 20%；37 模板迁移清单完成；483 项 OK | 按主题回滚 |
| **P4 HTMX 局部刷新** | 列表分页/筛选、图表数据区、通知已读改片段路由 | 无整页刷新；401/403 降级与 v1.7.12 行为一致；CSP 零违规 | 去掉 hx 属性即回滚 |
| **P5 slot 化 + 深色定稿** | registry `ui_fragments` + 6 slot 接管；两主题视觉定稿 | 插件注册 UI 片段无需改 base.html；两主题截图验收 | 按 slot 回滚 |

每阶段结束都要跑：`manage.py check` / `ruff check .` / 全量测试 / **CSP 真机四项冒烟**（两主题图表渲染、控制台零 CSP 报错、确认框、401·403 回归）。

---

## 七、CSP 硬约束（每次前端改动必过）

**禁止**（会被 nonce-only 策略拦）：
- 内联 `<script>`（除带 `{{ request.csp_nonce }}` 的极少量）、内联 `<style>`（`style-src` 仍为 `'unsafe-inline'` 但不要再新增）
- 内联事件属性 `onclick=` 等
- `eval` / `new Function` / 字符串定时器
- `hx-on:`、`hx-vals="js:…"`、`js:` 表达式
- 动态 `setAttribute('nonce')`（CSP3 不生效，v1.7.16 已实测证伪）

**允许**：
- 外部 `.js`（`script-src 'self'`）
- 带服务端 nonce 的内联脚本（每个响应同一值）

**新增前端能力的最低验收**：该功能在真实浏览器里跑一遍，`securitypolicyviolation` 监听零条违规（v1.7.16 已验证该探针有效，方法见 `docs/plugin-dev-v1716.md` §7）。

---

## 八、风险与不做

**风险**
1. **HTMX 局部刷新 + 现有 CSRF**：`hx-post` 需带 CSRF（走 `hx-headers` 或 `csrf-token` meta），否则 403；
2. **深色化会放大视觉回归面**：37 个模板全要目视验收，需建截图基线；
3. **slot 机制引入后**，base.html 会成为"插件间接耦合点"，需明确"slot 内片段失败的降级（空渲染）"；
4. **两主题同时重塑**，容易做出一套好一套垮，必须先定 corporate-clean 再复制契约。

**不做**
- 不引入 React / Cordis / pnpm（除非负责人明确改选路线 C 并授权测试基线重写）；
- 不引入 `django-csp` 或任何 CSP 放宽；
- 不迁移 ECharts（图表继续用现有实现）；
- 不合并两套主题；
- 不做一次性大改名（`.r-*` 类名保留，新组件用新名）。

---

## 九、已拍板（2026-11-12，负责人确认）

1. **统一到 DSH**：业务页与首页同一套视觉语言，不再保留"蓝灰企业风"。
2. **程度**：连业务页一起重排（外壳 + 配色 + 30 个业务模板的组件形态），不是只换色板。
3. **Risograph**：也换成 DSH，不再保留荧光粉 + 硬边套印的印刷风。
4. **深色**：业务页要深色，与首页共用同一个开关（同一 Cookie、同一 `data-color-mode`）。
5. **起点**：不单独做 P0 基线冻结，直接进入 D1（见下）。

### 9.1 新的阶段划分（取代 §六 的 P0–P5）

| 阶段 | 范围 | 文件 | 判据 |
|---|---|---|---|
| **D1 设计系统 + 外壳** | `--ds-*` token（浅/深）、`r-*` 兼容映射、`base.html` 换 DSH 通栏侧栏、`home.html`/`login.html` 适配、深色开关统一 | `themes/corporate-clean/` 4 个文件 + 开关后端 3 个文件 | 30 个业务页零模板改动即变 DSH 视觉；深浅切换可用；全量测试绿 |
| **D2 业务页重排** | 表格 / 表单 / 徽标 / 按钮组 / 空状态 / 图表容器 / 树形，逐页核对组件形态 | 30 个业务模板 | 每页截图与 DSH 组件对照；`style=` 只减不增 |
| **D3 Risograph 跟随** | Risograph 的 CSS 与骨架换成同一套 DSH 视觉 | `themes/risograph/` | 两主题切换后视觉一致 |
| **D4 验收** | 全量测试 + CSP 四项 + 深浅对比度 + 截图基线 | — | 496 项 OK、CSP 零违规、WCAG 达标 |

### 9.2 D1 期的硬约束

- **类名不改**：业务模板里是 `r-card` / `r-btn` / `r-table` / `r-input` / `r-badge` / `r-menu-link`，D1 只重定义这些类的视觉，**30 个业务模板一行不动**。这是"零模板改动拿到新皮肤"的前提。
- **裸色值归零**：重写后的 CSS 里，除 token 定义段外不出现裸十六进制。
- **深色靠语义层**：组件只消费 `--ds-*` alias，深色只替换 alias 取值，不改任何规则块。
- **DSH 规矩必须守住**（见 §5.1）：背景分层不靠色差靠圆角与内距；状态色不当底色托字；描边用同一黑/白的四级透明度；hover 只叠色不上浮。

### 9.3 执行状态（2026-11-12）

**已完成**

- **D1**：`corporate-clean.css` 全量重写为 `--ds-*` token 层（浅/深双套 alias、`--r-*` 兼容映射、Bootstrap 5.3 `--bs-*` 桥接、全部 `r-*` 组件重定义）；`base.html` 换成 `ds-shell` / `ds-rail` / `ds-main` 通栏侧栏（侧栏 `position: sticky` + `100vh` + 内部滚动，底部控件常驻）；`login.html` 去掉 logo 方块并加 `data-color-mode`；深色开关统一到 `oa_color_mode`（context processor + `/theme/mode/` 路由 + 视图 + settings 注册），首页 `assistant` 改用同一套常量。
- **D3**：`risograph.css` 改为 `@import` 同一份 DSH CSS，`themes/risograph/templates/{base,home,login}.html` 复制为同一外壳 —— 单源维护，改一处两主题同步。
- **图表跟随**：`charts/echarts/static/js/echarts.js` 的调色板从 `--r-pink`（DSH 下它是品牌近黑，导致序列全黑）改为 `--ds-state-*`；tooltip 底色/描边/文字改消费 `--ds-*`；gauge 进度环与中心数字补齐 —— 深浅两态图表不再黑白单色。
- **门禁**：`manage.py check` 0 issue、`ruff check .` 全绿、全量 **496 项 OK**。
- **真机**（headless Chrome 1440×900，`/dashboard/`、`/plugins/approval/`）：浅 `#ffffff` / `#0f1115` / 侧栏 `#f9fafb` 280×900、卡片圆角 16、控件高 32、徽标 999px；深 `#151517` / `#f9fafb` / `#1b1b1c` / 卡片 `#232324` / 徽标 `#353638` / 描边转白 6%；两态 `cspViolations: []`。

**未完成**

- **D2**：30 个业务模板**未逐页核对组件形态**。当前只靠 token 层统一视觉（已抽查审批中心、考勤签到详情两页，归口一致），162 处几何内联 `style=` 一处未减。
- **D4**：CSP 四项真机冒烟、深浅对比度数值计算、截图基线未做。

---

*本文不含实现代码；确认后按阶段逐个交付，每阶段单独提交与验收。*
