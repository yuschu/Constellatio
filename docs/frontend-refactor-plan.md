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

### 9.4 交互机制移植（v2.0.5）

D1 统一的是视觉；本节搬的是**机制**，首页（assistant 自带外壳）与业务页（`base.html`）共用同一份实现。

**参数来源（读源码，不做像素采样）**

| 机制 | 源码位置 | 取值 |
|---|---|---|
| 侧栏折叠 | `dsh-client-ui-sidebar` `SidebarRoot.collapsed` | rail 64px、padding `18px 10px 6px`、图标行 36×36、`gap:12`、logoRow 高 36 且 `margin-bottom:12` |
| 设置入口 | `dsh-client-ui-settings-general` `Trigger` | 行高 42、内缩 `paintInset 3px`、label 与 glyph `gap:10`、右侧 hint 悬停 `opacity 0→1` |
| 设置面板 | 同上 `Panel` | `800×800`（`min(800, 100vh-48)`）、`grid-template-columns: 188px`、标题 `padding 22px 12px 8px 24px`、navCell 40px、options `padding 0 24px 24px`、行 `padding 16px 0` + `.5px` 底边、`radius-panel 28` |
| 已开始会话的输入区 | `dsh-client-ui-conversation` `ConversationRoot[data-phase=active]` | `position: sticky; bottom: 0` + 顶部 36px 渐变、`overflow-anchor: none` |
| composer 自增高 | `dsh-client-ui-chat` `Composer` | `min-height 52`（hero）/`36`（docked）、上限 `336`、Enter 发送 / Shift+Enter 换行 |

**交互行为**（`plugin_host/static/js/ds-shell.js`，外部脚本，无内联，符合 CSP）

- 折叠：`html[data-rail-collapsed="true"]` 驱动；记忆写 `localStorage` 键 `dsRailCollapsed`；折叠态指针进入侧栏即回宽，移出复收。
- 设置：`[data-ds-settings-open]` 打开 `#ds-settings`；Esc / 点遮罩（仅 `e.target === modal`）/ 关闭按钮收起；关闭后焦点回到触发控件；`Mod+Alt+,` 切换；打开时 `body.ds-modal-open` 锁滚动，焦点落到当前分区。
- composer：`scrollHeight` 自增高、超 336 转内部滚动；`isComposing` 或 `dataset.composing` 期间回车不发送。
- 键盘可达：自绘按钮统一 `outline: none` + `:focus-visible` 自绘指示，不依赖 UA 默认焦点框。

**真机实测**（1440×900，headless Chrome + CDP）

| 项 | 首页 `/` | 业务页 `/dashboard/` |
|---|---|---|
| 展开 rail | 280 | 280（菜单行 36 高） |
| 折叠 rail | 64，toggle 36×36，设置入口 36 | 64，toggle 36×36，设置入口 36 |
| hover 回宽 | 280，设置入口回 42 | 280，设置入口回 42 |
| 设置面板 | 800×756，列 `188px 612px` | 800×756，列 `188px 612px` |
| composer | 52 → 244，上限 336，hero 上下留白 263/263 | — |
| Esc 关闭并还焦 | 是 | 是 |

**未做**：设置面板目前只出「通用」一个分区（DSH 有十余组，按需再拆）；侧栏「更多」的溢出菜单仍是占位入口。

### 9.5 插件页与侧栏顺序（v2.0.6）

原「插件开关」（`plugins/workspace`，`/plugins/workspace/`）在首页侧栏落在「更多」抽屉里、在业务页侧栏平铺末尾。本轮把它提到「助手」之后、「看板」之前并改名「插件」，页面本体按 DSH 插件清单形态重做。

**排序机制**：菜单 dict 新增 `order` 键，`plugin_host/registry.py:get_menus()` 末尾做一次稳定排序（`menus.sort(key=lambda m: m.get('order', 100))`），缺省 100 保持插件注册序 —— 插件注册顺序是启动契约，不被界面排序反绑架。助手 1 / 插件 2 / 看板 3；首页的 `PRIMARY_MENU_URLS` 扩为 `('/', '/plugins/workspace/', '/dashboard/')`（元组顺序即渲染顺序，同 URL 只取第一条）。

**参数来源（`dsh-client-ui-settings-plugin-inventory/lib/client.js` 的 CSS 字面量，非截图采样）**

| 元素 | 取值 |
|---|---|
| section | `max-width 760`、`gap 14` |
| heading / intro | `18 / 600`；`13 / lh 20`、label-tertiary |
| search | `height 36`、`padding 0 34 0 36`、`13px`、`radius-md`、focus 时 `border-color focus-ring` + `0 0 0 2px` 18% `color-mix` |
| cards | `grid-template-columns: repeat(2, minmax(0,1fr))`、`gap 10`、`≤520px` 单列 |
| card / cardContent | `border .5px` + `radius-xl`；`min-height 52`、`padding 12 / 14`、`gap 2`、hover `interactive-bg-hover` |
| cardTitle / description | `14 / 500 / lh 20`；`12 / lh 18` 两行 clamp + `text-wrap pretty` |
| identity chip | 等宽 `12 / 18`、`radius-xs`、`padding 1px 6px`、`bg-module-platform` |
| brokenNote（warning） | `color-mix(state-error 8%)` 底、`padding 8 / 10`、`12 / 18` |

token 映射：`settings-card-stroke→border-l3`、`settings-card-fill→bg-layer-1`、`interactive-bg-hover→interactive-hover`、`bg-module-platform→bg-layer-2`、`focus-ring-color→focus-ring`、`state-error-primary→state-error`。选择器全部 `.ds-plugins*` / `.ds-plugin*`，落在 `corporate-clean.css` 第 25 节；Risograph 靠 `@import` 跟随，未改其任何文件。

**新增控件（DSH 没有的）**：DSH 插件清单只有状态点、没有启停开关，本项目自绘轨道 `36×20` + 圆点 `16`（勾选态 `--ds-state-business`），原生 `input[type=checkbox][role=switch][data-plugin-switch]` 仍是唯一真值载体，`row.protected` 的插件换成 `span[role=switch][aria-disabled]`「系统必需」。

**真机实测**（1440×900，headless Chrome + CDP）

| 项 | 值 |
|---|---|
| 首页侧栏 | `助手 / 插件 / 看板 / 更多`，active = 助手 |
| 业务页侧栏 | `助手 / 插件 / 看板 / 部门 / …`（order 生效；v2.0.9 起删掉重复的「工作台」，见 9.9） |
| 插件页 | 13 卡、两列 `375px 375px`、卡高 134、`bodyMinH 52`、`padding 12px 14px` |
| 字号 | 标题 `14/500/20`、页头 `18/600/26` |
| 搜索 | `height 36`、`padding 0 34 0 36`；输入 `charts` 后可见卡片 1 |
| 开关 | 轨道 `36×20`、12 个 checkbox + 1 个「系统必需」、4 个 warning 块 |
| 深色 | body `rgb(21,21,23)`、卡片 `rgb(35,35,36)` |

**门禁**：`check` 0 issue、`ruff` 全绿、全量 **497 项 OK**（新增 1 条顺序锚定用例；`tests_registry._expected_menus` 参考实现同步应用同一排序键，否则等价断言只测到两侧各自的遍历顺序）。

**9.5 时列的两条遗留已在 9.9 收敛**：业务页侧栏「看板」与「工作台」同指 `/dashboard/` 的重复入口已删（只留「看板」）；msgid 也已进 `django.po` 并可编译 —— 项目自带 `tools/compile_mo.py`（纯 python 的 .po→.mo，不需要 gettext），`.mo` 能重编，不再靠「英文界面回落中文」兜底。

### 9.6 账号入口与账号菜单（v2.0.7）

侧栏底部不再平铺「设置 / 消息 / 我的 / 登出」四件套：只留一个账号入口（头像 + 名字），点开后才出现菜单，菜单里是「设置 / 消息 / 登出」；「我的」改到设置面板的独立分区。业务页（`themes/corporate-clean/templates/base.html`，Risograph 同源复制只换 CSS 路径一行）与首页（`plugins/assistant/templates/assistant/home_chat.html`）两处同改。

**参数来源（`dsh-client-ui-settings-account/lib/client.js` 的 `css$3` 常量，规则前缀 `.yHnPSG_`；菜单表面取自 `dsh-web-frontend/dist/assets/index-lh_YM6sT.css` 与 `dsh-client-ui-theme/lib/client.js`）**

| 元素 | 取值 |
|---|---|
| `_trigger` | `height 44`、`padding 6px`、`border-radius radius-md`、`gap 8`、`font-size 14`、`user-select none`、hover `interactive-bg-hover` |
| 未登录 trigger | `height 32`、`line-height 20`（与已登录同 padding） |
| 折叠态 trigger | `width 36`、`height 36`、`padding 0`、`justify-content center`、`gap 0` |
| `_avatar` | `24×24`、`border-radius 50%`、`bg-skeleton`、`color label-tertiary` |
| `_label` | 单行 `ellipsis` |
| `[role=menu]` | `min-width 124`、`max-width 280`、`padding 4` |
| `[role=menuitem]` | `border-radius radius-md`、`gap 8`、`min-height 40`、`padding 8 10`、`14 / lh 22`、图标槽 `16×16` |
| `_surface` | `border-radius radius-lg`（compact 走 `radius-md`） |
| `_material` | `position absolute; inset 0; z-index -1`、`background menu-surface-fill`、`backdrop-filter menu-backdrop-filter` |

token 映射：`interactive-bg-hover→interactive-hover`、`bg-skeleton→bg-skeleton`（首页 `--as-*` 侧无 skeleton，等值取 `--as-border-l1`：`#0000000a` / `#ffffff0f`）、`menu-surface-fill→浅 #fcfdfeb3 / 深 #303136a3`（源码里就是色值，不做 token 抽象）、`menu-backdrop-filter→blur(40px) saturate(150%)`、`menu-icon→label-secondary`、描边 `0 0 0 .5px border-l3`。菜单宽度：源码 `min-width 124` 是未登录菜单的缩窄值，已登录项「图标 + 设置 + Ctrl+Alt+,」实测 140 会把快捷键挤到文字上，取 `min-width 180` 容纳一行。

**结构与交互**（`plugin_host/static/js/ds-shell.js` 新增 `initAccount`）

- 入口：`button.ds-account__trigger[aria-haspopup=menu][aria-expanded=false][aria-controls=ds-account-menu]`；菜单 `div.ds-menu[role=menu][hidden]` = `ds-menu__material`（材质层）+ `ds-menu__list`；三项依次「设置（`data-ds-settings-open`，带齿轮 SVG 与快捷键）」「消息（`notify:notify_list`，`notify_unread` 时带 badge）」「登出（`form POST auth:logout`，带退出箭头）」。
- 开合：点击切换；Esc 收起并把焦点交还入口；点菜单外收起；点任一项都先收菜单（点「设置」时随后由 `initSettings` 开面板，因此面板打开时菜单必已收起）。触发控件若已随菜单隐藏，设置面板关闭后的焦点回退到账号入口——否则 `focus()` 落在不可见元素上、实际掉到 `body`（本轮实测发现并修掉）。
- 设置面板：nav 两个 cell（`data-ds-settings-tab="general" | "account"`），options 是两个同格位面板（`data-ds-settings-panel`），`initSettingsTabs` 切换 `hidden` 与 `is-active`/`aria-current`；显式补 `.ds-settings__options[hidden]{display:none}` 兜住将来给 options 加 `display` 的回归。

**真机实测**（1440×900，headless Chrome + CDP，`/` 与 `/dashboard/` 各跑浅深两态）

| 项 | 值 |
|---|---|
| 账号入口 | `264×44`（业务页 `263×44`）、`padding 6`、`radius 12`、`gap 8`、`14px` |
| 头像 | `24×24`、`radius 50%`、底色浅 `rgba(0,0,0,0.04)` / 深 `rgba(255,255,255,0.06)` |
| 菜单 | `180×128`、`radius 16`、`padding 4`、位于入口上方 6px；材质浅 `rgba(252,253,254,0.7)`、深 `rgba(48,49,54,0.64)`、`blur(40px) saturate(1.5)` |
| 菜单项 | 3 项各 `40` 高、`padding 8px 10px`、`lh 22`、`14px` |
| 折叠态 | 入口 `36×36`、`padding 0`、`gap 0`，侧栏 `64` |
| 设置面板 | `800×756`；nav 两 cell 切换后 `general hidden / account 可见`（反之亦然） |
| 焦点 | Esc 关面板后 `activeElement` = `ds-account__trigger`（浅深两态、两页均如此） |

**踩坑**：Django 模板的 `{# … #}` 不支持跨行，写成两行会把注释原文渲染到页面上（本轮实测截图捕捉到，改用 `{% comment %}`）。检查口径：逐行找「含 `{#` 但不含 `#}`」的行。

**门禁**：`check` 0 issue、`ruff` 全绿、全量 **497 项 OK**（本轮无新增用例——侧栏底部结构无既有断言，模板改动靠真机实测覆盖）。

**CSP 口径（本轮纠正一次假绿）**：先用「页面里读一个恒空数组」判断零违规，实际那个变量从未被赋值，读数恒为 `[]`。改成在文档创建时注入一个带标记的内联脚本做自证：该脚本确实不执行（`blocked`），说明 `script-src` 真在拦；在此前提下首页与业务页的侧栏折叠、菜单开合、设置分区切换、输入框自增高全部照常工作，即页面没有依赖任何被拦资源。浏览器日志通道（`Log.entryAdded`）在 headless 下没吐 `Refused` 条目，故未作为计数依据；静态侧仍由既有 `plugin_host/tests_csp.py` 覆盖。

**已知未收敛**：`ds-rail__user / ds-rail__settings / ds-rail__actions / as-user-row / as-settings-trigger / as-foot-actions` 等旧类名的样式规则仍留在两份 CSS 里（模板已不再输出，属死规则，未删以免牵动折叠态/hover 一串派生规则）；菜单不带 `_dsh-context-menu-in/out` 进出动画（源码动画时长 token 未在已查文件中找到，标未确认）；新增 msgid（「账号菜单」「我的」「打开」「登录状态」「登出」等）同样未进 `.po`。

---

## 9.7 侧栏收起：点击切换（v2.0.8）

**源码真值**（`dsh-client-ui-sidebar/lib/client.js` + `dsh-client-ui-layout/lib/client.js`）

- 切换算子：`toggleSidebar: (d) => { if (viewportWidth < 1024) narrowExpanded = !narrowExpanded; else sidebar = sidebar === 0 ? 280 : 0 }` —— 宽视口就是 `280 ↔ 0`，收起后的轨宽由 `collapsedWidth = drawer || darwin || windowsTitlebar ? 0 : 56` 决定，浏览器场景即 **56**。
- 不持久化：`dsh-client-ui-layout` 整文件没有 `localStorage / sessionStorage`，`layoutInfo` 初值 `sidebar: 280`。刷新即展开。
- 点击：`onClick: () => toggleSidebar()`，没有 debounce；`aria-label` = `collapsed ? toggle.open : toggle.collapse`；`aria-keyshortcuts` 取该快捷键的 aria；**没有 `aria-expanded`**。
- 快捷键：`id: "sidebar.left.toggle"`，`defaults.web:windows = { code: "KeyB", modifiers: ["primary", "alt"] }` → `Ctrl+Alt+B`（desktop 口径是 `primary+B`）。
- 收起 = slide + crossfade（源码注释原话）：宽度过渡只挂在 `[data-animating]:not([data-dragging]) .hHd-Xa_root`（`width var(--ds-transition-duration-slow) var(--ds-ease-in-out)`，即 `.3s cubic-bezier(.4,0,.2,1)`）；宽内容冻结在展开宽度、原地淡出；`COLLAPSE_SETTLE_MS = 150` 后 `settled = true`，宽内容卸载、上方控件自 `translateX(49px)` 淡入（`rail-in .15s`），底部只淡入（`rail-fade-in .15s`）。
- 展开：`wide` 类带 `wide-in .2s`（`opacity 0 → 1`）。
- 落位几何：根 `padding: 18px 10px 6px`；`logoRow 36 / margin-bottom 12 / padding 0`；`iconButton 36×36 / radius-md / label-primary`；`panelList gap 12 / margin-bottom 12`；`panelRow 36×36 / padding 0 / 居中`；`footArea align-items: center`；`settingsArea / footerActions` `width auto`、居中。
- 焦点：`useLayoutEffect` 在 `collapsed` 时若焦点落在侧栏内，`focusWithoutRing([data-sidebar-toggle])`。
- **没有 hover 回宽**：折叠态 `@media (hover:hover)` 只做一件事 —— toggle 的 `railMark`（品牌 mark）与 `panelIcon` 互换；整栏不会因指针进入而展开。

**落地差异**

- 折叠宽 `64 → 56`，padding 同步改 `18px 10px 6px`（§9.6 记录的 64 是上一版值，本版覆盖）。
- 删除「指针进入即回宽」整段：上一版是按观感加的，源码没有这个行为；收起只能点 toggle 或按快捷键解除。
- 宽度过渡收进 `[data-rail-animating]`，常驻过渡删掉。
- 布局切换点从 `collapsed` 挪到 `settled`：`collapsed` 只负责宽度与裁切，150ms 后才落 36×36，对应源码 `settled`。
- 移除 `aria-expanded`，补 `aria-keyshortcuts="Control+Alt+B"`。
- 去掉 `localStorage` 记忆（源码如此）。**这条会改手感**：刷新后回到展开态；若要保留记忆需另行决定，不属于源码行为。

**真机数值**（1440×900，本地 8011，浅深 × 首页/业务页各一轮）

| 时刻 | 实测 |
|---|---|
| 展开 | 宽 `280`、padding `6px 8px`、toggle `28×28`、行宽 `264 / 261`、gap `2` |
| 点击后 40ms | 宽 `278.4`（首页）/`280`（业务页起步帧）、`data-rail-animating=true`、transition `0.3s`、toggle 已 `36×36` |
| 点击后 170ms | 宽 `92.4 / 147.8 / 106.2 / 124.3`（四组）、`data-rail-settled=true`、行宽 `36`、gap `12`、动画名 `as-rail-in / ds-rail-in 0.15s` |
| 点击后 430ms | 宽 `56`、padding `18px 10px 6px`、transition 归 `0s` |
| 指针进入侧栏 | 宽仍 `56` |
| 焦点回位 | 焦点先放侧栏行 → 折叠后 `activeElement` = `BUTTON.as-rail-toggle / BUTTON.ds-rail__toggle` |
| `Ctrl+Alt+B` | 宽回 `280`、toggle `28×28`、aria 回「收起侧边栏」 |

**踩坑**

1. 只改宽度不够：DSH 折叠态 `logoRow` 里只渲染 toggle（品牌是 `wide &&` 才出）。本项目原来把品牌行缩到 36，结果「C」标记与 toggle 并排挤在一行（业务页折叠截图直接可见），已改为折叠态整个隐藏品牌链接。
2. `padding` 被常驻 transition 带着插值。业务页 `.ds-rail` 原本挂 `transition: width .2s, padding .2s`，折叠落位那帧 padding 还在动（实测 40ms 读到 `6.39px 8.06px`）。已改为 `transition: none`，只由 `[data-rail-animating]` 提供宽度过渡。

**已知未收敛**

- DSH 折叠态 toggle 平时显示 `railMark`（品牌 mark 24）、`hover` 才换 `panelIcon`；本项目按要求去掉了 logo，`railMark` 的占位元素不存在，折叠态固定显示面板/箭头图标，`hover` 互换自然失效。
- 宽度过渡与落位共用一条时间轴（150ms 落位 / 300ms 滑完），中间约 150ms 存在「图标已落 36、列还在收」的重叠帧。DSH 用 grid track 裁切 + 内容冻结规避，本项目是 flex 列，用 `overflow: hidden` 近似 —— 观感对齐，机制不同。
- 首页新增 `--as-dur-slow: 0.3s`（与 `--ds-dur-slow` 等值），业务页直接复用已有 `--ds-dur-slow`。

## 9.8 侧栏展开态对齐（v2.0.9）

9.7 只收敛了收起态。本轮按 `dsh-client-ui-sidebar/lib/client.js` 第 116 行的 `css$` 常量（单行 10,899 字符，格式化后 102 条规则，编号 00–102）逐条比对展开态，只改字面量不符的四处，不做像素采样。

| DSH 规则 | 源码字面量 | 本项目落点 |
|---|---|---|
| `[34] .logoRow` | `justify-content: flex-end; gap: 8px; height: 60px; padding: 8px 0 8px 8px; overflow: hidden` | `.as-logo-row` 已是 `flex-end`；`.ds-rail__brand` 原为 `justify-content: flex-start`，改 `flex-end`，并删掉第 24 节里覆盖成 `space-between` 的重复块 |
| `[36] .brand` | `min-width: 0; flex: 1; padding: 0; display: inline-flex; overflow: hidden` | `.ds-rail__brand a` 补 `flex: 1`，品牌可点区撑满到 toggle 前（实测首页 220 / 业务页 227） |
| `[96]–[100] .footArea` | 只有 `flex-direction: column; flex: none`，无分隔线、无内边距、无外边距 | `.ds-rail__foot` 去掉 `border-top: .5px`、`padding: 8px 0 4px`、`margin-top: 8px`，高度 57 → 44 |
| `[45] / [49] .iconButton` | 展开 `28×28`、折叠 `36×36` | 已对齐，未改 |
| `[50]` | 折叠态 `.toggle .panelIcon { display: none }`（`railMark` 常显） | 本项目去掉了 logo，`railMark` 占位元素不存在，折叠态固定显示 panelIcon，见 9.7 的已知未收敛 |

**折叠按钮图标换真值**。`IconPanelLeftOutlineRegular` 是 sprite 引用 `M("panel-left-outline", "regular")`，描边宽度由 `Vp = { regular: 1, medium: 1.3 }` 决定 → regular **1**。原始 SVG 串（`dsh-web-frontend/dist/assets/index-BgUyXZcc.js` 第 567536 字符，`size: 16`）：

```html
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="1">
  <path d="M13.5 1.5H2.5C1.94772 1.5 1.5 1.94772 1.5 2.5V13.5C1.5 14.0523 1.94772 14.5 2.5 14.5H13.5C14.0523 14.5 14.5 14.0523 14.5 13.5V2.5C14.5 1.94772 14.0523 1.5 13.5 1.5Z" stroke="currentColor"/>
  <path d="M5.5 1.5V14.5" stroke="currentColor"/>
</svg>
```

三处模板（`home_chat.html`、corporate `base.html`、risograph `base.html`）把原来的 chevron 换成这两条 path，`<svg>` 根补 `fill="none"`（否则 path 无 fill 时会被填成实心块）。尺寸走源码的 `size={wide || windowsTitlebar ? 16 : 18}`：`.as-rail-toggle > svg / .ds-rail__toggle > svg` 16px，`html[data-rail-collapsed="true"]` 下 18px。

**品牌 mark「C」移除**。源码 `logoRow.children` 是 `[wide && brand, toggle]`，品牌本身不含 mark 元素，toggle 里的 `railMark` 只在 `!wide` 渲染。本项目既已去 logo，三处模板的 `<span>…C</span>` 与两份 CSS 的 `__mark` 规则（含折叠段的 `[data-rail-settled]` 覆盖）一并删除。

**真机数值**（1440×900，容器 `:8000`，浅深 × 首页 / 业务页各一轮，与本地 `:8011` 逐项一致）

| 项 | 首页 | 业务页 |
|---|---|---|
| rail | `280 × 804` | `280 × 804` |
| logoRow | `x8 264×60`，padding `8 0 8 8`，gap `8`，justify `flex-end` | `x8 263×60`，justify `flex-end` |
| brand | `x16 220×24` | `x16 227×24`，gap `6` |
| toggle | `x244 28×28`，radius `8` | `x243 28×28` |
| foot | `x8 264×44`，padding `0` / margin `0` / borderWidth `0` | `x8 263×44`，同 |
| 折叠后 | rail `56`、brand `display: none`、toggle `x10 w36`、行 `x10 w36`、`data-rail-settled=true` | 同 |

`newBtn` 声明 `border: .5px solid` 与源码 `[57]` 一致，`getComputedStyle` 读回 `1px` 是 Chrome 对亚像素边框的取整，未改。

### 9.9 「看板 / 工作台」合并（v2.0.9）

`/dashboard/` 与 `/` 在侧栏各有一个入口，指向同一处业务大盘：

| 入口 | 注册处 | URL |
|---|---|---|
| 看板 | `plugins/assistant/apps.py`（order 3） | `/dashboard/` |
| 工作台 | `plugins/auth/apps.py`（`menus=[{'label': _('工作台'), 'icon': '⌂', 'url': '/'}]`） | `/` |

v2.0.0 起 `/` 已被 assistant 接管成对话首页，于是这条「工作台」既与「助手」同 URL、又与「看板」同指业务大盘，是纯重复。首页侧栏早有去重（`PRIMARY_MENU_URLS` 只取 2 条，`tests_assistant_home` 有断言），**只有业务页平铺全部菜单**，所以重复只在业务页可见。合并按「删重复入口 + 统一名字」两步：

| 改动 | 文件 | 内容 |
|---|---|---|
| 删菜单 | `plugins/auth/apps.py` | `menus` 改空列表。auth 是登录/登出插件，本身不需要侧栏入口；`PluginMeta.__init__` 用 `menus or []`，空菜单合法 |
| 标题统一 | `themes/corporate-clean/templates/home.html`、`themes/risograph/templates/home.html` | `<title>` 与 `<h2>` 的 `{% trans "工作台" %}` 改「看板」（各 2 处），页面标题与侧栏入口同名 |
| 错误页文案 | `templates/400.html`、`403.html`、`404.html`、`500.html` | 「返回工作台」→「返回首页」。目标 URL 本来就是 `/`（对话首页），旧文案已名不副实 |
| i18n | `locale/en/LC_MESSAGES/django.po` / `.mo` | 新增 `看板 → Dashboard`、`返回首页 → Back to home`；旧两条（`工作台 → Workspace`、`返回工作台 → Back to workspace`）保留 —— `plugins/language/tests.py` 的 gettext 契约用例仍以 `_('工作台')` 为样本 |

`.mo` 由 `python tools/compile_mo.py` 重编（`compile_all()` 扫 `locale/*/LC_MESSAGES/*.po`），`.mo` 是构建产物、不进版本库。断言随之更新：「英文界面必须是英文」的口径不变，只是文案换了名字 —— `plugins/language/tests.py` 两处、`plugin_host/tests_error_pages.py` 一处的期望值从 `Workspace` / `Back to workspace` 改成 `Dashboard` / `Back to home`，不是放宽。

**真机实测**（1440×900，本地 `:8011` 与容器 `:8000` 各一轮，浅色 / 英文 / 深色）

| 项 | 值 |
|---|---|
| 中文 `title` / `h2` | `看板 · Constellatio` / `看板` |
| 英文 `title` / `h2` | `Dashboard · Constellatio` / `Dashboard`（`.mo` 生效，不再回落中文） |
| 业务页侧栏 | `助手 / 插件 / 看板(active) / 部门 / 用户 / 角色 / 审批中心 / 待我审批 / 抄送我的 / 公告中心 / 考勤 / 签到详情 / 考勤规则 / 留痕链 / 组织架构 / 消息中心` —— 无「工作台」 |
| 首页侧栏 | `助手(active) / 插件 / 更多`，同样无「工作台」 |

插件菜单在 `apps.ready()` 注册，改 `apps.py` 必须重启 runserver（`--noreload` 下旧进程会保留菜单）或重建容器 —— 本地复测时踩过一次：首次改完仍见「工作台」，杀掉监听进程重启后消失。

**门禁**：`check` 0 issue、`ruff` 全绿、全量 **497 项 OK**（`e51b7c1` 时的 497 条基线，无新增、无 skip、无放宽）。容器重建后 8 个文件 MD5 与本地逐一相同。

### 9.10 考勤紧跟看板 + 首页「更多」按 DSH PanelMoreMenu（v2.0.10）

**考勤顺序**：业务页侧栏原为 `助手 / 插件 / 看板 / 部门 / … / 考勤 / 签到详情 / 考勤规则 / …`。考勤是最日常的业务入口，提到看板之后：`plugins/attendance/apps.py` 的首条菜单加 `'order': 4`，其余两条（签到详情、考勤规则）保持缺省 `order 100` 的注册序。`get_menus()` 的排序键是稳定的，所以只有考勤提前，`签到详情 / 考勤规则` 的相对位置不动。`plugin_host/tests_registry.py` 的顺序契约补一条锚定：`/dashboard/` 必须排在 `/plugins/attendance/` 之前。

**「更多」重做**。DSH 的实现在 `dsh-client-ui-sidebar/lib/client.js:240-286` 的 `PanelMoreMenu`：

| 元素 | 源码字面量 |
|---|---|
| anchor | `button.panelRow`（与面板行同形），`aria-haspopup="menu"`、`aria-expanded={open}`，点击 `setOpen(v => !v)` |
| anchor 图标 | `IconAppsAddOutlineRegular`，`size: wide ? 16 : 18` |
| 图标 SVG（sprite `apps-add-outline`，regular 描边 1） | 三个 `rect`（`2.25/2.25`、`2.25/9.75`、`9.75/9.75`，各 `4×4`、`rx 1`）+ `path "M11.75 1.75v5M9.25 4.25h5"` |
| 浮层 | primitives `Menu`：`portal: true`、`autoFocus: true`、`className: moreAnchor`、`listClassName: moreMenu` |
| `.moreAnchor`（规则） | `flex-direction: column; display: flex` |
| `.moreMenu`（规则） | `width: 288px; max-width: calc(100vw - 24px)` |
| 菜单项 | 由 `sidebar.panellist.actions` 槽渲染（各面板的 pin / 显隐 action） |

本项目原来是 `<details class="as-more">` + `<ul class="as-more__list">`（summary 与行同形、列表在侧栏内向上弹）。改为：

| 落点 | 做法 |
|---|---|
| 模板 `plugins/assistant/templates/assistant/home_chat.html` | `<button class="as-panel as-more__anchor" data-as-more-trigger aria-haspopup="menu" aria-expanded="false" aria-controls="as-more-menu">` + `div.ds-menu.as-more__menu#as-more-menu[role=menu]`，菜单表面复用账号菜单的 `.ds-menu`（上一轮已按 DSH 菜单材质做过） |
| 图标 | 换成 `apps-add-outline` 原文（16px、`fill="none"`、`stroke-width 1`） |
| `.as-more` | `display: flex; flex-direction: column`（对齐 `.moreAnchor`） |
| `div.as-more__menu` | `position: fixed; width: 288px; max-width: calc(100vw - 24px)`，覆盖 `.ds-menu` 默认的 `absolute / bottom 100% / max-width 280`（用 `div` + class 提高特异性，避免被后面的 `.ds-menu` 规则压回） |
| 定位 | `ds-shell.js` 的 `initMore()` 按 `getBoundingClientRect()` 摆放：上下空间取大的一侧、不遮挡 anchor、水平夹在视口内 —— 等价 DSH `Menu portal` 的浮层行为，且不会被侧栏 `overflow` 裁切 |
| 限高 | 空间不足时 `max-height` 收到可用高度 + `overflow-y: auto`（DSH 源码没有这条，是 13 项菜单在 804px 视口下的必要兜底；DSH 的 actions 菜单只有几条，不会触发） |
| 交互 | 点击切换、点外部关闭、`Esc` 关闭并回焦、点菜单项关闭、`resize` 重新摆位（同 `initAccount`） |
| 折叠态图标 | 新增 `html[data-rail-settled="true"] .as-panel__glyph .as-ico { width: 18px; height: 18px }`，对齐 `size = wide ? 16 : 18` |

**真机实测**（1440×900，本地 `:8011`，浅 / 深 / 折叠）

| 项 | 值 |
|---|---|
| 业务页侧栏顺序 | `助手 / 插件 / 看板 / 考勤 / 部门 / 用户 / 角色 / 审批中心 / 待我审批 / 抄送我的 / 公告中心 / 签到详情 / 考勤规则 / 留痕链 / 组织架构 / 消息中心` |
| 首页主入口 | `助手 / 插件 / 看板 / 更多`（`primary_menus` 仍 2 条 + 插件 + 更多） |
| 更多 anchor | `x8 264×36`，glyph `16×16`，4 条 path（3 rect + 1 path） |
| 更多浮层 | `288×528`，`position: fixed`，`radius 16`、`padding 4`；浅色材质 `rgba(252,253,254,0.7)` + `blur(40px) saturate(1.5)`，深色 `rgba(48,49,54,0.64)` |
| 浮层位置 | 展开态 `(8, 268)` —— anchor 下方 4px 起，13 项完整可见；折叠态 `(10, 298)`、高 498 并 `overflow-y: auto` |
| 折叠态 | `data-rail-settled=true`、glyph `18×18`、anchor `x10 w36` |

**门禁**：`check` 0 issue、`ruff` 全绿、全量 **497 项 OK**。`tests_assistant_home.test_sidebar_caps_entries_and_hides_rest_in_drawer` 的锚点从 `as-more__list` 改到 `data-as-more-trigger` / `id="as-more-menu"`（结构变更，断言仍要求「更多」承载业务菜单）。

## 9.11 「更多」菜单按 EntryMenuContent 重做（常用入口 + 浏览/创建插件）

上一轮把「更多」的外形换成了 `PanelMoreMenu`，但菜单内容还是把「其余业务菜单」一股脑塞进去（13 项）。
这一轮按 DSH 的 `EntryMenuContent` 重做内容，并把用户定的语义落地：**常用入口 + 浏览更多插件 + 创建你的插件**。

### 源码真值（逐条来自文件，不取样不推断）

| 来源 | 事实 |
|---|---|
| `dsh-client-ui-entry-customization/lib/client.js:33-72` `EntryMenuContent` | 折叠面板行是 `MenuItemButton`（只有 label；`active` 时右侧 `IconCheckOutlineRegular(16)`）；「浏览更多插件」= `MenuItemButton` + `IconPluginPinwheelOutlineRegular(16)`，`separatorBefore: moreEntries.length > 0`；「创建你的插件」= `MenuItemButton` + `IconPlusOutlineRegular(16)`，`separatorBefore: !browsable && moreEntries.length > 0` |
| 同文件 `:77-91` locale zh | `install: "浏览更多插件"`、`create: "创建你的插件"`、`createPrompt.sidebar: "创建一个带左侧栏入口的 DSH 插件。"` |
| 同文件 `:195-213` `apply` | `browsePlugins()` → `pluginNavigation.openList()`；`createPlugin()` → `uiWorkspace.startSession(undefined, { agentPreset: "cordis", prompt: t("createPrompt.sidebar"), whenDraftExists: "append" })` |
| en 文案 | `"Browse other plugins"` / `"Create your plugin"` |
| `dsh-client-ui-sidebar/README.md:44`（中文 `README.zh.md` 同款） | 「**The default More menu only offers plugin browsing and creation, without panel rows or pin controls.**」 |
| 全包 grep `inject("sidebar.panellist.actions")` | 只有 `dsh-client-ui-entry-customization` **一个**注册者 → DSH 的「更多」里**不存在「收起侧边栏」条目** |
| `dsh-client-ui-sidebar/lib/client.js:240-286` `PanelMoreMenu` | anchor `button.panelRow`（`aria-haspopup="menu"` / `aria-expanded`），图标 `IconAppsAddOutlineRegular`，`size = wide ? 16 : 18`；浮层 `Menu`（`portal: true` / `autoFocus`），`className moreAnchor` / `listClassName moreMenu` |
| `dsh-web-frontend/dist/assets/index-lh_YM6sT.css` 菜单行 | `._item`：`min-height:34px; padding:6px 8px; gap:6px; border-radius:var(--dsw-radius-md); font-size:13px; line-height:20px; color:label-primary`；hover `interactive-bg-hover`；`._itemIcon` `14×14`（`color: menu-icon`）；`._itemLabel` `flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap`；`._check` `14×14; flex:none; color:label-primary`；`._separator` `height:.5px; margin:3px 8px; background:border-l2` |
| 图标 sprite（`index-BgUyXZcc.js`） | `plugin-pinwheel-outline` 四条 arc path、`plus-outline` = `M8 2V14` + `M2 8H14`、`check-outline` = `M2.25 8.5L5.49732 11.7473C5.90519 12.1552 6.57263 12.1344 6.95426 11.7018L13.75 4`；regular 描边 `1` |
| `dsh-client-ui-sidebar` locale | `panels.more`: zh `更多` / en `More` |

### 本项目落地

| 落点 | 做法 |
|---|---|
| `plugins/assistant/views.py` | 新增 `COMMON_MENU_URLS`（考勤 `/plugins/attendance/` → 待我审批 `/plugins/approval/pending/` → 抄送我的 `/plugins/approval/cc/` → 审批中心 `/plugins/approval/` → 公告中心 `/plugins/notice/` → 消息中心 `/plugins/notify/`）、`CREATE_PLUGIN_PROMPT`；`_split_menus` 改为返回 `(primary, common)`；context 增加 `common_menus` / `create_plugin_url` / `draft_prompt` |
| 模板 | 更多菜单 = `common_menus` 循环（`span.ds-menu__label` + active 时 `span.ds-menu__check` 内 check SVG）→ `div.ds-menu__sep[role=separator]` →「浏览更多插件」（pinwheel SVG，`/plugins/workspace/`）→「创建你的插件」（plus SVG，`{{ create_plugin_url }}`）；两处 `textarea` 改为 `>{{ draft_prompt }}</textarea>` 承接预填 |
| 两份 CSS（`assistant.css` / `corporate-clean.css`） | `.ds-menu__item` 40/8-10/14px → DSH 真值 **34 / 6px 8px / gap 6 / 13px / line-height 20**；`.ds-menu__icon` 16 → **14**；新增 `.ds-menu__label`（ellipsis）、`.ds-menu__check`（14×14 / label-primary）、`.ds-menu__sep`（`0.5px / margin 3px 8px / border-l2`） |
| `locale/en/LC_MESSAGES/django.po` | 追加 `更多→More`、`浏览更多插件→Browse other plugins`、`创建你的插件→Create your plugin`；`tools/compile_mo.py` 重编，`django.mo` 35,303 B（不进版本库） |
| 测试 | `tests_assistant_home` 的 `more_menus` 断言改为 `common_menus`，并新增两条动作文案断言 |
| 折叠补充 | toggle 的 `:focus-visible` 从 `box-shadow` 换成 DSH 的 `outline: 2px solid #4176e6; outline-offset:-2px`（dark `#7aaaff` = `deepseek-400`）；折叠态补 `border-radius: radius-md` + `color: label-primary`（`dsh .collapsed .iconButton`）；两份 CSS 同步 |

### 设计取舍（为什么不是逐字照搬）

1. **常用 6 项来自 `get_menus` 按 URL 白名单挑**：DSH 的这些行来自 `panellist.actions` 槽（各面板自己注册），本项目没有那个槽，等价的来源是插件注册的 `PluginMeta.menus`，用 URL 白名单保证顺序与「考勤紧跟看板」的既有口径。
2. **「创建你的插件」用 `/?prompt=` 预填**：DSH 的 `createPlugin()` 走 `uiWorkspace.startSession(prompt)` 起新会话；本项目的等价动作是带 prompt 回首页并填进输入框（`whenDraftExists: "append"` 在本版没有草稿机制，预填即止）。
3. **「更多」里不放「收起侧边栏」**：DSH 的 `sidebar.panellist.actions` 只有 entry-customization 一个注册者，README 也明确写了默认更多菜单只有浏览与创建两条；本项目照此执行，折叠开关只保留在 `logoRow` 的那一个 toggle 上（不重复进菜单）。

### 真机实测（1440×900，本地 `:8011`）

| 项 | 浅色 | 深色 |
|---|---|---|
| 菜单行 | 8 行（考勤 / 待我审批 / 抄送我的 / 审批中心 / 公告中心 / 消息中心 / 浏览更多插件 / 创建你的插件），每行 **34px** | 同 |
| 动作行图标 | **14×14**（pinwheel / plus 各 1） | 同 |
| 分隔线 | `0.5px`、`margin 3px 8px`、`rgba(0,0,0,0.1)`、y=479 | `0.5px`、`margin 3px 8px`、`rgba(255,255,255,0.12)` |
| 浮层 | `(8,268)` `288×287`、`radius 16`、`padding 4` | 同 |
| check | 无（首页 active 为 `/`，6 项常用均非当前页） | 同 |

### 折叠排查结论

- 单击 toggle **同步生效**：`collapsed=true`、`animating=true`、`aria-label` 变「打开侧边栏」，400ms 后 `settled=true / w=56`；再点一次回 `collapsed=null / w=280`。
- 业务页 `:8011` 实测：`280 → 56`，行宽 `271 → 36`（居中 `x10 w36`），行间 gap `12`（36 + 12 = 48 步进），折叠态 `nav` `overflow-y:auto`。
- 折叠态 toggle：`(10,18) 36×36`，与 `dsh .collapsed{padding:18px 10px 6px}` + `.collapsed .iconButton{36×36}` 一致。
- 菜单里不再有任何「收起/折叠」条目 —— 两条动作行之外只有 6 条业务入口（上一轮的 13 项混排已去掉）。

### 「收了又自己弹回」：状态没跨页，不是交互丢了

排查方式：`setAttribute/removeAttribute` 打点 + 12 次采样（0.4s 步长）。结果折叠属性只被写一次（`sync` 在 `ds-shell.js:43-52`，调用栈来自 toggle 的 click），12 次采样一直是 `w=56 / settled=true` —— 单页内没有任何东西回写。

真正原因是**换页**：DSH 的 `layoutInfo.sidebar` 存在 SPA 客户端内存里，翻路由不丢；本站是 Django 多页，任何导航（点「更多」里的条目、点账号菜单、点门户入口）都会重新初始化，`sync(false, false)` 把侧栏拉回 280 —— 观感就是「收了又自己弹回」。

| 落点 | 做法 |
|---|---|
| `plugin_host/static/js/ds-shell.js` | 新增 `RAIL_STORE_KEY = 'constellatio.rail-collapsed'`，`sync()` 结尾 `writeStoredRail(collapsed)`，初始化从 `sync(false, false)` 改为 `sync(readStoredRail(), false)`；用 **sessionStorage**（会话内保持、关标签页清空），不写 localStorage，与 DSH「不跨会话持久化」的口径一致 |
| `plugin_host/static/js/rail-boot.js`（新增） | 在 `<head>` 同步读同一个键并先把 `data-rail-collapsed` / `data-rail-settled` 落到 `<html>`。`ds-shell.js` 是 `defer`，实测冷导航会先出现一帧 `280`（`loading|280|null` → `complete|56|true`），首帧脚本把这个跳变去掉 |
| 三个模板 | `home_chat.html`、`corporate-clean/base.html`、`risograph/base.html` 的 `</head>` 前加 `<script src="{% static 'js/rail-boot.js' %}"></script>`（同步、同源，CSP 不需要 nonce） |
| 测试 | 新增 `test_rail_collapsed_state_booted_before_first_paint`：首页与 `/dashboard/` 都引用 `js/rail-boot.js`、引用位置在 `</head>` 之前、脚本里出现同一个键名 |

**实测（`:8011`）**

| 场景 | 结果 |
|---|---|
| 首页点收起 → 去 `/dashboard/` → 回首页 | `56 / collapsed=true / settled=true` 全程保持 |
| 折叠态点「更多」→ 考勤页 | `56` 保持 |
| 再展开 → 去 `/dashboard/` | `280` 保持 |
| 冷导航首帧 | 有元素的第一帧就是 `56|true`，不再有 `280` 中间态 |
| 会话键 | `sessionStorage['constellatio.rail-collapsed']` 随点击在 `1 / 0` 之间切换 |

## 9.12 侧栏「助手」→「考勤」+ 看板移植 dsh-context（v2.0.11）

两处改动：① 侧栏顶部第一格由「助手」换成「考勤」（「+ 新会话」本身就是助手入口，再单列一条指回 `/` 只是重复入口）；② `/dashboard/` 的版式整体换成 [dsh-context](https://github.com/bowenliang123/dsh-context) 的 Context Dashboard（Apache-2.0，源码已克隆到 `.tmp-test/dsh-context`，只取版式与字面量，不引它的构建链）。

### 9.12.1 侧栏第一格：助手 → 考勤

| 落点 | 做法 |
|---|---|
| `plugins/assistant/apps.py` | `menus` 只剩「看板」一条（`order 3`），删掉 `{'label': _('助手'), 'icon': '✦', 'url': '/', 'order': 1}`；注释写明「首页入口就是侧栏顶部的『+ 新会话』」 |
| `plugins/assistant/views.py` | `PRIMARY_MENU_URLS` 首项 `/` → `/plugins/attendance/`（顺序：考勤 → 插件 → 看板）；`COMMON_MENU_URLS` 去掉 `/plugins/attendance/`（考勤已在固定入口，不在「更多」里重复），剩待我审批 / 抄送我的 / 审批中心 / 公告中心 / 消息中心五项 |
| `plugins/assistant/templates/assistant/home_chat.html` | 图标分支由 `{% if menu.url == '/' %}`（星形）改为 `{% if menu.url == '/plugins/attendance/' %}`（日历 + 勾：`rect rx=1.5` + `M2.25 6.5h11.5` + 两条装订线 + `M5.6 10.2l1.55 1.55 3.1-3.1`），其余 `workspace` / `else` 分支不变 |
| `plugin_host/tests_assistant_home.py` | `test_duplicate_home_menu_highlights_only_first` → `test_primary_panel_starts_with_attendance`（断言 primary 顺序 = 考勤 → 看板、`as-panel is-active` 计数 0、`common_menus` 不含考勤）；`test_sidebar_caps_entries_and_hides_rest_in_drawer` 的 `len(primary_menus)==2` 保留并改注释（普通账号 2 条：考勤 / 看板；「插件」入口要 `workspace_manage`） |
| `plugin_host/tests_registry.py` | `test_menu_order_assistant_plugin_dashboard` → `test_menu_order_plugin_dashboard_attendance`（`get_menus` 注册序 = 插件 2 → 看板 3 → 考勤 4，并断言 `/` 已不在菜单里） |

事实口径：普通账号 `primary_menus = ['/plugins/attendance/', '/dashboard/']`（2 条），管理员 3 条 + 「更多」。首页已无指向 `/` 的菜单，`as-panel is-active` 计数为 0。

### 9.12.2 看板：dsh-context 的版式（源码真值）

| 来源 | 事实 |
|---|---|
| `src/client/styles/overview.css:1-21` | `lc-ov-page`（整屏面板）→ `pagescroll` → `pagecontent{padding:0 10px 10px}`；`page .lc-card{padding:10px 12px}`；`pagehead{padding-top:28px;margin-bottom:24px}`；`pagetitle{20px/28px/500;margin:0 8px 0 0}` + `settings` 胶囊 + `headctl`；`first{repeat(2,minmax(0,1fr));gap:10px;margin-bottom:10px}` |
| `:24-26` | `kpis{repeat(3,minmax(0,1fr));gap:8px}`、`kpi{align-items:center;padding:8px}`、`kpi .lc-stat-value{font-size:20px}` |
| `:35-60` | `usage-plot{--lc-ov-usage-axis-top-inset:13px; grid-template-columns:42px minmax(0,1fr) 42px; grid-template-rows:minmax(56px,1fr) auto; gap:6}`；柱 `width:10px;border-radius:3px 3px 0 0`；左侧 `tokens` 蓝 72%、右侧 `cost` 绿 72%；`@container lc-ov (max-width:400px)` 只留奇数日并隐藏数值 |
| `:62-79` | `stats{repeat(2,...);gap:10px;margin-bottom:10px}`、`@container (max-width:700px)` 降单列；`tiles{repeat(4,...)}`、`tile{height:280px;overflow:hidden}` + `tile-body{overflow-y:auto}`、`@640 两列`、`@560 单列` |
| `:82-122` | 热力 `cell 20×20;border-radius:20%`、`lc-heat-0..4` 用 `color-mix` 16/28/50/72/92%、legend `10×10`；`tally` 隔行 stripe + `dot 7px` + `name mono 11px` + `bar 2px/opacity .45` |
| `src/client/styles/base.css:22-32` | `lc-card{radius 10px;padding 14px 16px}`（浅色 `radius 12px`）；`lc-card-title`，浅色下加 `padding-bottom:7px;margin-bottom:9px;border-bottom:.5px` |
| `src/client/styles/stats.css:1-31` | `lc-stat{background:bg-layer-2;border:1px solid border-l2;radius 8px;padding:6px}`；`lc-donut-track{stroke:color-mix(neutral-500 18%)}`；中心 `b`/`span` 两级 |
| `src/client/components/overviewUsage.tsx` | `TICKS=[0,25,50,75,100]`；`heightOf=max(4, round(v/max*100))`；每列两根 `lc-ov-usage-bar`；日期取 `key.slice(5)` |
| `src/client/components/donut.tsx` | `viewBox 0 0 42 42`、`r=15.9155`（周长 100）、`stroke=4`、`dasharray="${len} ${100-len}"`、`offset=100-acc+25`、`cut=min(0.5/2, len/4)` |
| `src/client/components/heatmap.tsx` | 8 周 × 7 天、`sundayOfWeek` 回溯 `7*(weeks-1)`、`levelOf` 阈值 0.25/0.5/0.75、周标签只标一/三/五、月标签只在 `wi===0 || 跨月 || 日===01` 显示 |
| 色板 | `categories.ts` 里**没有** `RING_COLOR`（grep 0 命中），本项目改用主题状态色 `--ds-state-business/success/warn/done/error` 作 5 色阶 |

### 9.12.3 数据契约（后端新增，前端只吃结构）

`plugin_host/workbench.py` 新增两段与 `range` 无关的序列（`build_dashboard` 返回值加 `insight`）：

| 键 | 内容 |
|---|---|
| `insight.usage7` | 近 7 天 `submitted / finished / submitted_height / finished_height`，`_height(v, peak) = 0 if v<=0 else max(4, round(v*100/peak))` |
| `insight.usage7_ticks` | `percent ∈ {0,25,50,75,100}`、`top = 100-percent`，左右 rail 各带自己的 max 刻度 |
| `insight.heat_cols` | 8 周 × 7 天，列带 `month` 标签，`future` 空格，`level` 按 `ratio<=0.25→1 / <=0.5→2 / <=0.75→3 / else 4`；`heat_weeks` 7 行只标一/三/五 |
| `insight.composition` | `_composition_of(flow)`：五类计数折环形段，`cut=min(0.25, len/4)`、`length-=2*cut`、`offset-=cut`、每段补 `rest`、段色 `tone=1..5` |
| `dept.max` | `max(headcount)`，供模板 `widthratio` |

OA 口径映射（DSH 是「按会话自身各请求时间归属」，本项目按单据的 `created_at` 归属）：

| DSH 指标 | 本项目口径 |
|---|---|
| 用量双柱（tokens / cost） | 每日「提交」= `Approval.created_at` 计数；「已办结」= 同批创建里 `status in ('approved','rejected')`；员工按 `applicant=user` 过滤 |
| 活跃度热力（sessions） | 管理员 = `Attendance` 当日 `Count('user', distinct=True)`；员工 = 本人当日有记录记 1（单位人天） |
| 环形（任务分布） | 五类单据计数（请假 / 报销 / 用章 / 外出 / 加班…），空态画 `lc-donut-track` 底圆 |

全部 `apps.get_model` 取模型 + `except (OperationalError, ProgrammingError)` → `_degraded('insight.approval')` / `_degraded('insight.attendance')`，插件关掉时看板不 500。

### 9.12.4 版式落点

| 落点 | 做法 |
|---|---|
| `plugin_host/templates/home_dashboard.html` | 全文重写（约 460 行，**无内联脚本**，原 echarts 段与 7 个 `wb-chart-*` 全删）：`lc-ov-page > lc-ov-pagecontent > lc-ov-pagehead`（h1 + 角色胶囊 + `.lc-gran` 范围切换）→ `.lc-ov-first`（5 张 KPI + 用量双柱卡）→ `.lc-ov-stats`（单据构成环形 + 类型/数量/占比 tally、部门概况 bar）→ `.lc-ov-tiles`（活跃度热力、单据类型、部门签到、流程快捷发起）→ 管理员「插件运维与组织数据」三卡 → 业务入口 / 公告简报 / 我的消息三个 `lc-ov-list` |
| `plugin_host/views.py` | `messages_preview` 提为变量，新增 `unread_count`（`is_read` 为假的条数）进上下文，供「未读消息」KPI 与消息卡角标 |
| `themes/*/templates/home.html`（corporate-clean / risograph 各 3 行） | 只留 `{% block content %}{% include "home_dashboard.html" %}{% endblock %}`，去掉 `r-hero` 二层标题（标题 / 角色 / 范围都在 pagehead 里，重复一层就是 DSH 没有的东西） |
| `themes/corporate-clean/static/.../corporate-clean.css` **第 26 节**（约 +900 行） | 新 token `--lc-blue/--lc-green/--lc-canvas/--lc-control-track/--lc-list-stripe/--lc-tone-1..5`（映射到 `--ds-state-*`）；照抄 DSH 的 `.lc-card` / `.lc-card-title` / `.lc-ov-page`（`container: lc-ov`）/ pagehead / pagetitle / settings 胶囊 / `.lc-gran` / kpis / kpi / usage plot / stats / tiles / 热力全套 / tally / grid / session / donut / 色阶 / 容器查询（932 / 700 / 640 / 560 / 400px 与 `640<w<=1020` 隐藏周标签）；`risograph.css` 仅 `@import` 同一份，不复制 |

### 9.12.5 两处与 DSH 有意不同（都写进 CSS 注释）

1. **`.lc-ov-page` 不锁高**：DSH 是整屏面板（`height:100%;overflow:hidden` + 内层 pagescroll），本项目的看板在文档流里滚，故放开 `height:auto` / 不裁切；视觉参数（padding / gap / 字号 / 圆角 / color-mix 比例）一个没改。
2. **`.lc-ov-stats` 加 `align-items:start`**：DSH 两栏等高是因为两张卡都满；本项目环形可能空、部门可能十行，等高会把空卡拉成一整片白。部门概况卡另按 `slice:":6"` 只列前 6 个部门，末尾补一行「共 N 个部门，全部见『部门签到』」。
3. **普通账号补第 5 张 KPI**：`kpis` 是 `repeat(3, ...)`，5 张刚好 3+2；没有 `approval_approve` 的账号原本只剩 4 张，第二行会空一格。现改为 `cards.mine`（本人提交、当前仍 `pending` 的单据数，实时口径）顶替「待我审批」那一格；同一账号的「部门签到」位（`dept` 只对管理员构建）换成「我的单据」，三行 = 审批中 / 已通过 / 已驳回，带条形，管理员仍是部门签到。

### 9.12.6 门禁 + 真机实测

| 项 | 结果 |
|---|---|
| `manage.py test plugin_host.tests_home plugin_host.tests_assistant_home plugin_host.tests_registry` | 53 tests OK |
| 全量 `venv/run_tests_shim.py` | 498 tests OK |
| `ruff check plugin_host plugins` | All checks passed |
| 结构计数（`/dashboard/`，headless Chrome CDP） | `hasPage=true`、`pageW 1118`（侧栏展开）、KPI 5、tiles 4、业务卡 14、环形段 5、热力格 61（56 格 + 5 图例）、双柱 14 根 |
| 首页侧栏 | `primary = ["考勤","插件","看板","更多"]`，`hasPage=false`（首页本就不是看板） |
| 深浅两态 | `.tmp-test/screens-dash/dash-light.png`、`dash-dark.png` 均通过：深色画布 `--ds-bg-base`、卡片 `bg-layer-2`、热力阶与浅色同比例 |

---

## 9.13 主页面板内切换 + 业务页侧栏去重 + 折叠换「返回主页」（v2.1.0）

目标：考勤 / 插件 / 看板三格不再跳业务页，改成在主页里换正文；业务页侧栏不再重复这三条入口；业务页侧栏的折叠按钮换成「返回主页」。

### 9.13.1 面板路由（后端）

| 落点 | 行为 |
|---|---|
| `/`（无 `panel`） | 对话态，`panel_key = chat` |
| `/?panel=attendance` | 首页外壳 + 考勤正文 |
| `/?panel=workspace` | 首页外壳 + 插件正文（需 `workspace_manage` 或超管） |
| `/?panel=dashboard` | 首页外壳 + 看板正文 |
| `/plugins/attendance/`、`/plugins/workspace/`、`/dashboard/` | **保留为深链**，主题壳 + 同一份正文 partial |

- `plugins/assistant/views.py`：`PRIMARY_MENU_URLS = HOME_PANEL_URLS`，新增 `PANEL_BY_URL` / `PANEL_TITLES`、`_resolve_panel()`（未知 key、权限不足一律回落 `chat`，不渲染半个面板）、`_panel_context()`（惰性 import 三个上下文构造函数并入首页上下文）、`_split_menus()` 在每条 primary 菜单上补 `panel_key` / `panel_url` / `panel_active` 三个字段，`menu.url` 仍保持原业务 URL。
- `plugin_host/views.py` 抽出 `dashboard_context(request)`、`plugins/attendance/views.py` 抽出 `attendance_context(request)`、`plugins/workspace/views.py` 抽出 `switch_list_context()`：业务页与首页面板**共用同一口径**，不存在两套数据拼装。
- `plugin_host/context_processors.py`：`HOME_PANEL_URLS = ('/plugins/attendance/', '/plugins/workspace/', '/dashboard/')`，`menus()` 同时给 `menus`（全量，首页用）与 `sidebar_menus`（过滤掉上述三条，业务页用）。
- 面板态挂主题表：`panel_theme_css = f'themes/{theme}/css/{theme}.css'`，只在 `panel != chat` 时挂（对话态本来只用 `assistant.css`；实测两者视觉基线一致，见 9.13.5）。

### 9.13.2 正文抽 partial

| 新文件 | 来源 | 关键处理 |
|---|---|---|
| `plugins/workspace/templates/workspace/_panel.html` | 原 `switch_list.html` 正文 + 内联脚本 | `switch_list.html` 缩成 3 行 include 壳；表单加 `next` 隐藏域 |
| `plugins/attendance/templates/attendance/_panel.html` | 原 `attendance_dashboard.html` 正文 | **重写为不依赖 bootstrap**：布局走 `.at-page/.at-head/.at-grid/.at-card/.at-form`，卡片表格按钮仍用主题 `r-*`；图表脚本从 `{% block extra_js %}` 搬进 partial 内部（`chart.script_url` + `chart.adapter_url` + nonce 内联 `oaChartRender`） |
| `plugin_host/templates/home_dashboard.html` | 上一轮已抽 | 直接被首页 include |

- 打卡与插件启停原先固定 `redirect('attendance:attendance_dashboard')` / `redirect('workspace:switch_list')`，面板态会把用户弹回业务页；现两处都加 `_return_url(request)`（`url_has_allowed_host_and_scheme` 校验 POST `next` 同源，缺省回原业务页），首页面板刷新后仍停在 `/?panel=...`。

### 9.13.3 前端切换（`plugin_host/static/js/home-panels.js`）

拦截 `[data-home-panel]` 点击（尊重 modifier / 中键；点当前面板直接 return）→ `fetch` 目标 URL 取整页 → `DOMParser` 抽 `[data-panel-body]` → 替换 `className` + `innerHTML` → `runScripts()`（把搬进来的 `<script>` 重新执行，考勤图表靠这一步画出来）→ `syncThemeCss()`（按新文档有无 `link[data-panel-theme]` 挂/摘主题表）→ `setSidebarActive()` → `document.title` → 滚动重置 → `history.pushState`；失败 `catch` 回退 `location.href = url`；`popstate` 重新 fetch 当前 URL。

**DSH 真值：面板切换没有过场动画。** 依据是 `dsh-web-frontend/dist/assets/index-lh_YM6sT.css` 的 `@keyframes` 全集——只有 `_dockHintIn_` / `_dockScrimIn_` / `_dsh-context-menu-in|out_` / `_dsh-plugin-detail-skeleton_` / `_dsh-row-shimmer-*` / `_dsh-state-dot-*` / `_dsh-toast-*` / `_indicator-enter_` / `_modalEnter_` / `_reveal-*-dot_` / `_spin_` / `_tooltip-in_`，没有 panel/page 过渡；侧栏自身只有 `hHd-Xa_wide-in`（0% opacity）与 `hHd-Xa_rail-in`。所以本轮实现是**即时替换**，不加淡入淡出——刻意对齐，不是漏做。

`panelActive` 的视觉照 `dsh-client-ui-sidebar/lib/client.js` 的 `PanelRow`：底色 `--dsw-alias-interactive-bg-hover`、文字仍 `label-primary`、行高 36px、3px 透明 border-inline。

### 9.13.4 业务页外壳

- `themes/*/templates/base.html`（两套同构）：删掉 head 的 `rail-boot.js`（业务页没有折叠态了，首帧还原不再需要）；`.ds-rail__toggle` 按钮换成 `<a href="/" class="ds-rail__toggle ds-rail__home" aria-label="返回主页">` + house 图标；侧栏循环 `menus` → `sidebar_menus`。
- `corporate-clean.css` 第 28 节：`.ds-rail__home` 收回链接色（主题全局 `a` 规则会把它染成链接蓝）、`.at-*` 考勤面板布局（`minmax(0,5fr) minmax(0,7fr)`，<900px 单列，`.at-grid > .r-card + .r-card{margin-top:0}` 抵掉 `.r-card + .r-card` 的上边距，`.at-card > .r-badge{align-self:flex-start}` 防止列向 flex 把徽标拉满整行）。`risograph.css` 只 `@import` corporate，无需改。
  - **返回主页按钮的几何**：品牌行里的 `.ds-rail__brand a`（`flex:1` / `height:24px` / 18px 字号，specificity 0,1,1）会把同一行里的返回按钮一并命中，把 `.ds-rail__toggle` 的 28×28 挤成 **127×24**。修法是 `.ds-rail__brand a.ds-rail__home` 显式收回 `flex:none / display:grid / 28×28 / min-width / 16px 图标 / hover 底色`，与首页 `.as-rail-toggle` 实测一致（两者 CDP 量出来都是 `box [28,28]`、`svg [16,16]`、`color rgb(97,102,107)`、`radius 8px`）。
  - **插件清单居中**：`.ds-plugins` 原本只有 `max-width:760`，没有 auto 外边距，760 的清单贴在 1102 内容区的左边（右边空 340）。补 `width:100% + margin-inline:auto` 后，首页面板与 `/plugins/workspace/` 都是落在列中线：CDP 量到业务页 `leftGap 200 / rightGap 200`，首页面板 `195 / 205`（差的 10px 是 `.as-panelview` 的 `scrollbar-gutter: stable` 预留，属正常）。
- `assistant.css` 第 27 节：`.as-main--panel` / `.as-panelbody`（flex column / flex 1 / min-height 0）/ `.as-panelview`（flex 1 / overflow-y auto / padding 20px 24px 40px / scrollbar-gutter stable）+ 两条桥接（`body.as-body .as-sidebar a` 收回链接色、`.as-panelview a` 用 `--ds-link`）。

### 9.13.5 门禁 + 真机实测（1440×900，本地 `:8011`）

| 项 | 结果 |
|---|---|
| 全量 `venv/run_tests_shim.py` | **501 tests OK**（基线 499 + 本轮 +2） |
| `ruff check plugin_host plugins` | All checks passed（`tools/*`、旧 migration 的 5 条 I001/F401/B007 为既有基线，非本轮引入） |
| 服务端冒烟 `.tmp-test/panel_smoke.py` | 7 个落点全 200；`/plugins/approval/` 无 `data-ds-rail-toggle`、无 `rail-boot.js`、侧栏不含 `/dashboard/` |
| 浏览器切换（CDP，`.tmp-test/flow.mjs`） | 对话态 → 考勤 → 看板 → 后退 → 回对话：`active` 依次 `chat/attendance/dashboard/attendance/chat`，`title` 同步，`themeLink` 面板态 true、对话态 false，`scrollTop` 每次归 0；**`window.__noReloadMark` 全程为 true、`performance.timeOrigin` 不变** —— 三次切换均未重新加载；点「+ 新会话」时 mark 丢失（真实导航，符合设计） |
| 截图 | `.tmp-test/screens-panel/dashboard.png`、`attendance.png`、`plugins.png`、`dashboard-dark.png`、`chat.png`、`approval.png` |
| 主题表注入对照 | 对话态强行注入 `corporate-clean.css` 前后截图（`chat-before.png` / `chat-after.png`）视觉基线一致 → 面板态挂表不会造成风格跳变 |

### 9.13.6 排查记录：模板热更新 + `--noreload` 的混合态

浏览器一度拿到「新模板类名 + 空面板正文 + 无主题表」的页面，服务端 test client 却完全正常。根因是 `:8011` 上还挂着**本轮改动之前**启动的 `runserver --noreload`（PID 早于 views.py 的修改时间）：模板在 DEBUG 下每次请求重读，Python 模块不会重载，于是出现「新模板 + 旧视图上下文」的混合态——`panel` 变量根本不存在，`{% if panel != 'chat' %}` 为真、三个 include 全不匹配。杀掉旧进程重启后一切正常。教训：**改 `views.py` / `apps.py` 必须重启进程或重建容器；模板热更新会掩盖这个差异。**

### 9.13.8 v2.1.1：业务页与考勤面板的原语回流（提交 `050760b`）

**取证方式**：不靠截图采样，直接解析 DSH 产物 `dsh-web-frontend/dist/assets/index-lh_YM6sT.css`（单行 minified，88k 字符），按 `input/field/table/row/button/card/badge/tag/list/header` 分组导出规则文本（`.tmp-test/dump_dsh_css.py`、`dump_dsh_css2.py`、`scan_btn.py` → `dsh_css_dump.txt`、`dsh_css_dump2.txt`）。原语模块在 `index-BgUyXZcc.js` 里以 `const FU=Object.freeze({Button:vi, Checkbox:tR, ...})` 导出，`dsh-client-ui-settings-shell` 等包只是调用 `@deepseek-ai/dsh-client-ui-primitives`；该包不在 `_npx` 缓存里，字面量只能从提取出的 CSS 规则取。

| 原语 | 字面量（DSH 源码） | 落到本项目 |
|---|---|---|
| Button `._button_1ulci_2` | inline-flex / gap 4 / radius-md / 14-22 / padding 0 14 / 透明底；`._md` height **36**；`._sm` height **28** / 12-18 / padding 0 10 / radius-sm；`._primary` 实心；`._outline` = `inset 0 0 0 .5px border-l3` | `.r-btn` 36、`.r-btn--sm` 28、`.r-table .r-btn` 28；行内非语义色按钮改 outline |
| Input `._input_181ew_115` | height **34** / padding 0 12 / border **.5px** border-l4 / radius-md / bg-layer-3 / 13-1.5；focus-visible 只换 border-color(state-business) | `.r-input/.r-select/.r-textarea` 同值；textarea 96 高 padding 8/12 |
| Field `._field_181ew_3` | column / gap **6** / padding **12px 0**；相邻 field 上边 `.5px border-l2` | `.at-field` gap 6；`.at-kv__row` padding 10 0 + 相邻分隔 |
| Table `._tableScroll` | th/td padding **10px 16px**；th 下边 `.5px border-l3`、td 下边 `.5px border-l2` | `.r-table th,td` `height:auto` + 同值 |
| Tag `._tag_brmue_4` | radius **999** / padding **1px 8px** / **11-17** / 500；tones 用 **10~12% color-mix** | `.r-badge` 同值，`--green/--orange/--blue/--pink` 改 color-mix |
| IconButton `._iconButton_3oazc_539` | 28×28 / padding 6 / svg 15 / radius-sm | 返回主页按钮沿用（9.13.4） |
| `._heading_121p8_19` / `._compactList` / `lc-card` | 分组头 11-16-500 tertiary；紧凑行 min-height 24；card padding 14px 16px、title 14/20/600 + 下分隔 | 卡片 `padding:14px 16px`、`.r-card` 去投影、`.at-card__title` 14/600 + `.5px` 分隔 |

token 映射：`label-primary-foreground → --ds-on-primary`、`bg-module-platform → --ds-bg-layer-3`、`state-business-primary → --ds-state-business`（本项目 token 里没有前两个同名变量）。

**模板改动**：`attendance/_panel.html` 的「本月统计」由 `<table class="r-table">` 换成 `<dl class="at-kv">` 两行（标签左、值右对齐，行间 0.5px 分隔），与 DSH 的 field 行一致；其余业务模板未改类名。

**表单排布**（CSS-only，写在 `.ds-main__body` 作用域内）：label 13/20 secondary + `text-transform:none !important`（模板里是 inline `.75rem` + uppercase，只能 `!important` 压）、help 12/18 tertiary、错误 12/18 error、`.mb-3` 间距 14、checkbox 16 + `accent-color` 品牌色、字段列 select 满宽。

**几何实测**（CDP，`.tmp-test/tableprobe.mjs`）：卡片 `padding 14px 16px`；`th` 41 高 `padding 10px 16px` 13/20；表行 `41`（纯文本行）/`49`（含 28 高按钮的行）；行内 `.r-btn` 28 高、padding 0 10、12-18。

**门禁与真机**：全量 `venv/run_tests_shim.py` **501 tests OK**；本地 `:8011` 与容器 `:8000` 各出浅/深两态图（`?panel=attendance`、`/plugins/user/users/`、`/plugins/user/users/new/`、`/plugins/approval/`、`/plugins/user/roles/`）；容器重建后按 MD5 对齐：`corporate-clean.css` 本地/容器均 `c4c358de0b24e8474dfcaa26ccfee6eb`、`attendance/_panel.html` 均 `6e3b6641a50a8242b846f0227ce6e7ba`。容器考勤面板有数据（2 天 / 2 次迟到），图表柱正常绘制。

### 9.13.9 v2.1.2：二级页（考勤规则 / 部门新建）按 DSH detail 移植

> **形态作废**：用户当场否决了这一版（原话「不对，不是这种二级页，是点开设置的那个页面」）。
> 本节保留为取证记录与历史对照；实际实现见 **§9.13.10（设置弹层形态）**。
> 其中唯一仍然成立的部分是「DSH 取值不看截图」的方法论，以及 `._detail*` 这组字面量的来源。

**取证方式**：仍不看截图。DSH 的「设置/详情二级页」不是独立框架页面，而是从插件页进入的**整页子视图**（`dsh-client-ui-settings-shell/README.zh.md` 明说「在侧栏打开插件，在官方分组里选择终端…」，它注册进 `plugins.item` slot，由 `dsh-client-ui-plugin-manager` 承载）。因此字面量直接从 `dsh-client-ui-plugin-manager/lib/client.js`（428KB）取：统一顶栏组件是 `function DetailTop({ crumbLabel, crumbText, onBack, icon, actions })`，三类详情（包 / 组件 / 行）与「更多」列表页共用；对应 CSS 以 `X_2TxG_` 前缀**内嵌在该 js 的 CSS 字符串里**（主 CSS bundle 搜不到这些类名）。

| DSH 类 | 字面量 | 落到本项目（`corporate-clean.css` 第 30 节） |
|---|---|---|
| `._detail` / `._detailTop` | column flex；`padding-top: var(--plugin-page-top-inset)` = **28px** | `.ds-sub` column flex |
| `._crumb` | 12.5px / `label-tertiary` / inline-flex / gap **6** / padding 0 / 无边框无底色；hover → `label-primary`；focus-visible → focus ring、offset 2 | `.ds-sub__crumb`（篇内 `a:not(...)` 特例，见下） |
| `._crumbIcon` | `transform: rotate(90deg)`（chevron-down 转朝左） | inline SVG 左向 chevron 14×14（`.ds-sub__chevron`） |
| `._detailHead` | margin **32px 0 0** / gap 12 | `.ds-sub__head` margin-top 32、gap 4 |
| `._detailTitle` | **20px / 500 / 28px** | `.ds-sub__title`（实测 20/500/28） |
| `._detailDesc` | `label-secondary` / **14 / 22** | `.ds-sub__desc` margin-top 8 |
| Field 行 | 相邻 **.5px border-l2** 上分隔 / padding **12px 0** / gap 6 | `.ds-field`（实测 padding 12/12、gap 6，边框同 `.at-kv__row`） |
| `._field` 文本 | label 13/20 secondary、help 12/18 tertiary、error 12/18 | `.ds-field__label/__help/__error` |
| `._moreBack` / `._pageTitle` | 返回按钮 28×28、`IconChevronLeftOutlineMedium size=20`；页标题 20/500/28 | 二级页头部同一颗 20/500 标题（本轮不做「更多」列表页） |

**考勤规则 = 考勤面板二级页**
- 路由：`/?panel=attendance&sub=rules`。`assistant/views.py` 新增 `PANEL_SUBS`（`attendance: ('rules',)`）、`_resolve_sub()`（未登记或**缺 `attendance_rule_manage`** 时退回上一级面板，不出 403，口径同 `_resolve_panel`）、`SUB_TITLES`（标题变「考勤规则」），`_panel_context(request, panel, sub)` 把 `attendance_context` 与 `rules_context` 合并，并注入 `in_home_panel` / `panel_sub` / `rules_entry_url` / `rules_back_url` / `rules_back_aria` / `rules_next`。
- 正文：新增 `attendance/_rules.html`（crumb「‹ 考勤」+ 标题 + 两行说明 + 6 个字段行 + 保存）。业务页 `attendance/attendance_rules.html` 变成 `{% include %}` 外壳，深链与整页形态都保留。
- 保存：`attendance_rules` 成功后 `_return_url(request)` 优先（沿用打卡已有的 host 校验），无 `next` 时仍回 `/plugins/attendance/rules/?saved=1`（既有断言不动）。面板表单带 `next=/?panel=attendance&sub=rules`，PRG 回面板并带 `saved=1`。
- 面板内导航：`home-panels.js` 把拦截面从 `[data-home-panel]` 扩到 `[data-panel-link]`（面板里的「⚙ 考勤规则」与二级页的 crumb 返回都走它），仍是 fetch → 换 `[data-panel-body]` → 重跑 script → `pushState`，`popstate` 逻辑不变。原先「点当前面板就 `preventDefault`」的短路要加一条例外：URL 带 `sub=` 时点侧栏「考勤」必须回上一级面板（实测 `?sub=rules` → 点侧栏 → `/?panel=attendance`，同样无刷新）。
- 样式冲突：`assistant.css` 的 `body.as-body .as-panelview a` 会把 crumb 染成链接蓝（`--ds-link`），改成 `a:not(.ds-sub__crumb)`（hover 的 underline 同样排除），实测 crumb 恢复 `rgb(129,133,140)` = `label-tertiary`，hover 变 `rgb(15,17,21)` = `label-primary`。

**部门新建 = 部门页二级页**
- `user/views.py::department_list`：`GET ?view=new` 渲染新模板 `user/department_form.html`（crumb「‹ 部门」+ 标题「新建部门」+ name/parent 两字段行 + 创建/取消）；`action=create` 校验失败**留在二级页**（原先回落到列表页右侧内联卡），成功仍 `redirect` 回列表。
- `department_list.html`：头部右侧加「＋ 新建部门」主按钮指向 `?view=new`，删掉右列常驻的「新建部门」card；`edit_dept` 时右列「修改部门」card 保留（原 POST edit 流程未动），列表在没有 edit 时恢复整行 12 栏。右列字段行同时换成 `.ds-field`（去掉 inline `.75rem/uppercase`）。

**几何实测**（CDP，`.tmp-test/subflow.mjs`，`/?panel=attendance&sub=rules`，本地 `:8011` 与容器 `:8000` 双端一致）：crumb `12.5px` + `rgb(129,133,140)` + gap `6px`；title `20px/500/28px`；字段 `padding 12/12`、`row-gap 6`；input **34**；主按钮 **36**；表单列 **760**。**无刷新证据**：点「考勤规则」→ crumb 返回 → `history.back()`，全程 `performance.timeOrigin`（docId）不变、`window.__noReloadMark` 保持，URL 依次 `/?panel=attendance` → `?panel=attendance&sub=rules` → 回来 → 再前进，侧栏 `.is-active` 始终是 `attendance`。

**门禁与真机**：全量 `venv/run_tests_shim.py` **510 tests OK**（新增 9 条：面板二级页 5 条 + 部门二级页 4 条）。容器 `docker compose up -d --build web`（`GUNICORN_WORKERS=3`）重建后 MD5 全对齐：`corporate-clean.css` `b02ca3d296142cbd293bcc0f0ae9b077`、`assistant.css` `443d3c6499067b6e0424ea9c9f928704`、`home-panels.js` `e01777d6e813dce9eaf6f5aed0ef3818`、`_rules.html` `ce06b91d865a6d5a58f332238a5e6d16`、`_panel.html` `5b76476d17c53592cf1c83525f69fd74`、`attendance_rules.html` `bfc825264d937baad8a7a8df5b7f6943`、`department_form.html` `0044520cee9cc96712d35a45dd269e65`、`department_list.html` `054d5ad5751eca8b4f7d14d9ef465c4a`、三个 `views.py` 与本地同哈希。深浅两态图存 `.tmp-test/screens-panel/sub-*.png`、`.tmp-test/screens-container/sub-*.png`。

**坑**：Django 的 `{# … #}` 是**单行**注释，多行会原样输出到页面（本轮首版两个模板都踩了，截图里整段注释出现在页面顶部）；多行一律用 `{% comment %}…{% endcomment %}`。

### 9.13.10 v2.1.2 二版：二级页 = 「点开设置的那一页」（设置弹层形态）

**形态结论**：二级页不是换掉面板正文，而是像 DSH 里点开设置一样，在 `document.body` 上盖一层设置弹层。同一份面板本体两处复用：首页面板里是弹层，业务页深链是 inline 卡片。

**取证（源码字面量，仍不看截图）**
- `dsh-client-ui-settings/lib/client.js` 是设置领域**底座**，自身不渲染 UI（`configForms` / `settingsMirror` / slot 投影）。
- `dsh-client-ui-settings-shell/lib/client.js` 的 `ShellCard` 只组合 `SettingsForm` + `SettingsValueField`（字段 = label + hint + input + 保存/丢弃），即「设置项」的粒度。
- 真正的外壳在 `dsh-client-ui-settings-general/lib/client.js`：`SettingsPanel` 用 `createPortal(document.body)` 挂 `overlay` + `mask` + `panel(role=dialog aria-modal)`；`renderSlot("settings.header")`，`nav` 由 `settings.section` 投影，`options` 放当前分区；关闭路径 = header ✕ / 点遮罩 / document Escape；`useModalLayer(panel, true, onClose)`。
- 面板 CSS（同文件第 60 行内嵌串，`VOzbGW_*`）：

| DSH 字面量 | 值 | 本项目落点（`corporate-clean.css` 第 12 节 `.ds-settings*`，二级页只加修饰类） |
|---|---|---|
| `overlay` | `position:fixed; inset:0; display:flex; align-items:center; justify-content:center; z-index:1000` | `.ds-settings`（第 12 节既有） |
| `mask` | `position:absolute; inset:var(--dsh-frame-chrome-top,0px) 0 0; background:var(--dsw-alias-bg-mask-1); backdrop-filter:var(--dsw-mask-blur)` | `.ds-settings__overlay`（`--ds-bg-mask` = `rgba(0,0,0,.24)`） |
| `panel` | `width:800px; height:min(800px, calc(100vh - 2*max(24px, var(--dsh-frame-overlay-top,24px)))); max-width:calc(100vw - 48px); border-radius:var(--dsw-radius-panel); background:var(--dsw-alias-bg-layer-2); box-shadow:var(--dsw-elevation-prominent); grid-template:"title header" "nav options" minmax(0,1fr) / 188px minmax(0,1fr); overflow:hidden` | `.ds-settings__panel`（实测 800×800，1440 视口下 x=320 居中） |
| `navTitle` | `padding:22px 12px 8px 24px; font-size:16px; font-weight:500; line-height:24px` | `.ds-settings__title`（`grid-area: title`） |
| `nav` | `padding:10px 12px 0`；`navList` column、`gap:4`、`overflow-y:auto` | `.ds-settings__nav` / `__cells` |
| `navCell` | `height:40; border-radius:radius-md; padding:9px 16px 9px 12px; gap:8; font-size:14; line-height:22`；active = `--dsw-specific-sidebar-nav-item-active` | `.ds-settings__cell`（本轮把左内边距由 16 修为 12，对齐字面量） |
| `header` | `height:54; padding:20px 14px 8px 10px; justify-content:space-between`；`close` 28×28 / `radius-sm` | `.ds-settings__header` / `__close` |
| `options` | `padding:0 24px 24px; overflow-y:auto` | `.ds-settings__options` |
| ≤767px | 移动端栅格变体（title 单行、nav 横排） | **未移植**（本项目桌面端优先，见 §9.13.7） |

**落点**
- 考勤规则：`attendance/_panel.html` 的正文永远是看板；`⚙ 考勤规则` 从面板内切页（`data-panel-link`）改成弹层触发器 `data-ds-modal-open="ds-attendance-rules"`（`href` 保留为无 JS 兜底）。看板末尾在 `perms.attendance.attendance_rule_manage` 且 `in_home_panel` 时 include `attendance/_rules_modal.html`。
- 弹层三段：`_rules_modal.html`（遮罩 + `data-ds-subpage*` 外壳）/ `_rules_panel.html`（`title` + `header` + 188px `nav` + `options`）/ `_rules_body.html`（两句 desc + 已保存徽标 + 6 个 `.ds-field` + 保存）。业务页 `attendance_rules.html` 只包一层 `.ds-settings--inline` 复用同一份 `_rules_panel.html`，右上 ✕ 变成返回看板的链接。
- 部门新建：`department_list.html` 头部「＋ 新建部门」改触发器，页尾 include `user/_department_new.html`（同款三段，`?view=new` 打开，创建/取消在 `options` 底部）。`user/views.py` 用 `_render_department_page()` 统一渲染，create 校验失败也让弹层保持打开（`dept_form_open=True`）。
- 地址栏是唯一真源：`?sub=rules` / `?view=new` 在 → 打开，不在 → 收起。`ds-shell.js` 新增 `initSubpages()`：文档级委托处理 `[data-ds-modal-open]` / `[data-ds-modal-close]`、Escape 关闭最上层、`popstate → sync()`，开时 `pushState` 到 `data-ds-subpage-url`、关时 `replaceState` 回 `data-ds-subpage-base`，焦点先落 `.ds-settings__cell.is-active`、关闭后还给触发器；暴露 `window.DSSubpage.sync()`，由 `home-panels.js` 在 `render()` 换完正文后调用（面板正文被整块替换时不丢行为）。
- `assistant.css` 撤掉 `a:not(.ds-sub__crumb)` 特例，恢复 `body.as-body .as-panelview a` 与 `:hover` 两条原规则（crumb 已不存在）。
- CSS 第 30 节整体重写：删 `.ds-sub*`，改成 `.ds-settings--subpage`（`z-index:1001` + `[hidden]{display:none}`）、`.ds-settings--inline`（`position:static`、面板 `height:auto; min-height:420px; margin:0 auto`）、`.ds-settings__desc/__status/__form/__actions`，并保留 `.ds-field*` 原语（含 `.ds-fields--card` 给部门「修改」右列）。

**无刷新与开合实测**（CDP，`.tmp-test/subpage.mjs`，本地 `:8011`）

| 步骤 | URL | 弹层 | `__noReloadMark` |
|---|---|---|---|
| 看板初始 | `/?panel=attendance` | `hidden` / `aria-hidden=true` | 1 |
| 点 ⚙ | `?panel=attendance&sub=rules` | 打开 / `aria-hidden=false` | 1 |
| 点 ✕ | `/?panel=attendance` | 收起 | 1 |
| Escape | `/?panel=attendance` | 收起 | 1 |
| 切到看板面板 | `/?panel=dashboard` | 节点随正文替换消失 | 1 |
| 切回考勤 | `/?panel=attendance` | 收起 | 1 |

几何：overlay 覆盖整视口（`0,0,1440,900`）、`position:fixed; z-index:1001`、遮罩 `rgba(0,0,0,.24)`；面板 `800×800`，`x=320,y=50`。

**门禁与真机**：全量 `venv/run_tests_shim.py` **511 tests OK**。测试按弹层形态重写：`AttendancePanelSubPageTests` 5 条（看板带 `#ds-attendance-rules` + 收起态 `hidden`、`?sub=rules` 时 `rules_open=True` 且看板仍在、无权限不渲染弹层、业务页 `--inline` 无 `--subpage`、POST→PRG），`DepartmentFormPageTests` 4 条（`?view=new` 弹层 + 列表仍在、列表页收起态、校验失败保持打开、成功 303）。容器 `docker compose up -d --build web`（`GUNICORN_WORKERS=3`）重建后 MD5 与本地逐文件对齐（值见本轮提交说明）。深浅两态图：`.tmp-test/screens-v2/rules-modal-light.png` / `rules-modal-dark.png` / `dept-new-light.png` / `dept-new-dark.png` / `rules-inline-light.png`。

**坑（重复踩了一次）**：Django `{# … #}` 只能单行；`attendance/_panel.html` 的 div 内多行注释又被原样渲染到页面顶部，截图才发现。多行一律 `{% comment %}`。

### 9.13.11 v2.1.3：7 个入口铺开 + 单分区不列左栏（提交 `7303c67`）

**用户两条口径**（看图后提出，逐字）
1. 「新建用户 新建角色 发起审批 发布公告 留痕链的查看 查看模板 消息中心都做成这样的」
2. 「页面中只有应该选项就没必要在左边列出来，移除然后将内容居中（按钮居中）」

第 2 条的依据：DSH 的 `nav` 是 `settings.section` 投影出来的**分区目录**（`navCell` 40 高、`gap:4`），多分区时它是导航，单分区时它只是「一条重复标题」的空目录。所以单分区页面把 `nav` 那一列从栅格里去掉，`options` 横跨整行。

**共享外壳**（新增两份，全部页面零重复）
- `plugin_host/templates/includes/ds_settings_panel.html`：面板本体。参数 `sp_title` / `sp_title_id` / `sp_body`（动态 `{% include sp_body %}`）/ `sp_modal` / `sp_back` / `sp_stack`（默认 560，`"wide"` = 720）。`sp_modal=True` 右上渲染 ✕（交给 `ds-shell.js`），`sp_modal=False` 且有 `sp_back` 时渲染返回箭头（深链页没有遮罩，✕ 会被读成关闭），两者都没有则 `header` 为空。
- `plugin_host/templates/includes/ds_settings_modal.html`：遮罩弹层外壳（`overlay` + 面板，`data-ds-subpage` / `sp_query` / `sp_url` / `sp_base` / `sp_open`，`hidden` 由 `sp_open` 决定）。
- 标题一律在 `{% block %}` 里 `{% trans "X" as sp_title_text %}`：子模板 `{% extends %}` 之后、block 之外的节点根本不执行，标题变量会是空串（本轮 5 个 inline 页踩过）。

**单分区 CSS**（`corporate-clean.css` 末尾，第 12 节之后）

| 规则 | 值 | 含义 |
|---|---|---|
| `.ds-settings--single .ds-settings__panel` | `grid-template-areas:"title header" "options options"`；`grid-template-columns:minmax(0,1fr) auto`；`grid-template-rows:auto minmax(0,1fr)` | 188px 分区列被移除，正文横跨整行（DSH 的 nav 列在这类页面里是空的） |
| `.ds-settings__stack` | `width:100%; max-width:560px; margin:0 auto` | 正文列 560 居中 |
| `.ds-settings__stack--wide` | `max-width:720px` | 两列内容（模板清单 / 留痕统计）用 720 |
| `.ds-settings__actions--center` | `justify-content:center` | 按钮行居中 |
| `.ds-settings--single .ds-settings__options` | `padding-top:var(--ds-space-2)` | 标题行已由 header 撑到 54，正文顶部只留 8 |
| `.ds-settings--inline .ds-settings__panel` | `height:min(800px, calc(100vh - 64px))` | 深链页也是同一块面板，高度照 DSH 字面量 800，内容多了在 `options` 里滚 |
| `.ds-field select[multiple]` | `height:auto; min-height:132px` | 角色权限是多选，不能被单行控件高度压扁 |

**落点（7 个入口 = 5 个表单 + 2 个只读）**
- 新建用户 / 新建角色：`user/views.py` 抽 `_render_user_list(request, form=None, form_open=False)` 与 `_render_role_list(...)` 作唯一渲染入口；列表页 `＋` 按钮 `data-ds-modal-open` + `?view=new`；新增 `_user_create_body.html` / `_role_create_body.html`（弹层与深链共用），深链页 `user_create_page.html` / `role_create_page.html` 只包 `.ds-settings--inline .ds-settings--single` + 共享外壳；校验失败回列表且 `form_open=True`。
- 发起审批：`_approval_list_context` + `_create_context(request, form=None, type_key=None, source=None, chip_prefix='?type=')`，chips 带 `href`（弹层里是 `?view=new&type=…`，切类型不丢弹层）；`approval_create` 三分支（重新申请 → 深链页；POST 失败 → 列表 + 弹层 + 字段错误；GET → 深链页）。
- 发布公告：`_render_notice_list(request, form_data=None, form_open=False)` 单入口；非法 POST 回列表弹层并用 `form_data` 回填（旧实现会丢字）。
- 查看模板：`structure/views.py` 抽 `_template_context(request)`；组织架构页 `?view=template` 开弹层，因 `role_rows` 键名冲突，弹层上下文用 `tmpl_` 前缀、`overview.html` 里映射回原名；无 `structure_view` 权限时既不渲染入口也不渲染弹层。
- 留痕链 / 消息中心：这两个没有父列表页，直接是 inline 面板（720），右上不渲染 ✕。
- 考勤规则 / 部门新建：同步收口到共享外壳（`nav` 列一并移除），`_rules_modal.html` / `_department_new.html` 只剩外壳 include，正文在 `_rules_body.html` / `_department_new_body.html`。

**几何实测**（CDP，`.tmp-test/geom7.mjs`，1440×900，本地 `:8011` 与容器 `:8000` 各跑一遍，结论一致）

| 路由 | 面板 | 栅格列 | `nav` | stack | actions |
|---|---|---|---|---|---|
| `/plugins/user/users/?view=new` | 800×800 @ `x=320,y=50` | `748px 52px` | 不渲染 | 560 @ x=440 | `center` |
| `/plugins/user/roles/?view=new` | 800×800 @ `x=320,y=50` | `748px 52px` | 不渲染 | 560 @ x=440 | `center` |
| `/plugins/approval/?view=new` | 800×800 @ `x=320,y=50` | `748px 52px` | 不渲染 | 560 @ x=440 | `center` |
| `/plugins/notice/?view=new` | 800×800 @ `x=320,y=50` | `748px 52px` | 不渲染 | 560 @ x=440 | `center` |
| `/plugins/structure/?view=template` | 800×800 @ `x=320,y=50` | `748px 52px` | 不渲染 | 720 @ x=360 | `center` |
| `/plugins/user/users/new/` 等 5 条深链 | 800×800 @ `x=460,y=32`（内容区内居中） | `748px 52px` | 不渲染 | 560 | `center` |
| `/plugins/blockchain/` `/plugins/notify/` | 800×800 @ `x=460,y=32` | `776px 24px`（无 header 按钮） | 不渲染 | 720 | — |

遮罩实测像素：面板外取点 `(1400,500)` = `rgb(194,194,194)`，即白底叠 `rgba(0,0,0,.24)`，与 `--ds-bg-mask` 一致。

**回归（首轮 5 failures 的根因）**
- `plugins/notice/views.py` 重构时用 `Substring` 拼接，误删 `notice_readers` / `notice_detail`（`manage.py check` 直接报 `module has no attribute`），已从 `HEAD` 原文补回。
- `@require_perm('notice_manage')` 被留在插入点上方，挂到了 `_render_notice_list` 上，`notice_create` 失去守卫（测试里表现为「无权限 POST 期望 403 实得 302」），已放回 `notice_create`。
- `@require_perm('approval_view')` 同样挂到了 `_approval_list_context`，`plugins/approval/` 落进 `LoginGuardSetTests` 的 bare 集合（护栏直接点名 `plugins/approval/`），已放回 `approval_list`。
- `plugins/approval/views.py` 用了 `reverse` 未 import → 两条路由 500。
- 审批类型 label 改成「审批类型」会让 `Select approval type` 的英文断言失效，已用回旧 msgid「选择审批类型」。
- `tests_csp` 的 `data-confirm` 计数点跟着正文搬到 `structure/_template_body.html`。

**断言口径注意**：全站设置弹层 `#ds-settings` 自身就有 `.ds-settings__nav`，所以「无左栏」不能用 `assertNotContains('ds-settings__nav')`，改用 `ds-settings--single` + `ds-settings__stack` + `ds-settings__actions--center` 三个类断言，DOM 侧用探针量 `navRendered`。

**门禁与真机**：全量 `venv/run_tests_shim.py` **511 tests OK**（116s）、`ruff check plugins plugin_host` 全绿；容器 `docker compose up -d --build web`（`SECRET_KEY` / `GUNICORN_WORKERS=3` / `OA_THEME=corporate-clean`）重建后 28 个改动文件 MD5 逐一对齐；容器上 12 条路由 GET 全部 200。深浅两态图：`.tmp-test/screens-v3/*-light.png` / `*-dark.png`（24 张），容器同批在 `.tmp-test/screens-v3/container/`。



1. 面板态不放 `as-header`（纯 `.as-panelview`，标题由各面板自己的 `.lc-ov-head` / `.at-head` 承担）。
2. 三个业务 URL 保留为深链，只从侧栏移除（若要去掉入口而非 URL，需再定）。
3. 双柱口径（提交 vs 已办结）、热力口径（人天签到）、看板「插件启用 / 未读消息」对普通账号的语义，仍按上一轮实现未验收。
4. 业务页表单卡片的宽度：v2.1.3 起 7 个入口的正文列统一是面板内的 560（两列内容 720），但 `user_form.html` / `role_form.html`（编辑）等仍是模板 inline 的 `max-width:560px`，且部分表单模板还有 inline `.75rem + uppercase`（目前靠 §29 的 `!important` 压制）——是否把这些编辑表单也逐个换到面板、并清 inline 待定。
5. 部门「修改」仍是 POST 驱动的右列内联卡（v2.1.3 只把「新建」收口到共享外壳）；是否同样改成设置面板未定。
6. 「留痕链的查看」按整页面板实现（统计 + 表格都在面板里）；若用户本意指单条记录详情，需要改成「列表点查看 → 记录详情弹层」。
7. 「消息中心」「留痕链」没有父列表页，所以做成 inline 无 ✕ 面板；若希望它们像其余 5 页那样从某个列表/看板弹层打开，需要指明父页。

---

*本文不含实现代码；确认后按阶段逐个交付，每阶段单独提交与验收。
### 9.13.12 v2.1.4：「需要切页的」二级页全面收口 + 修弹层提交死按钮（提交 `133c0db`）

**先说一个真 bug（v2.1.3 遗留）**：设置弹层里的表单 `<form method="post">` 没写 `action`，点「创建 / 保存」时 POST 打回**宿主列表页**，而宿主视图当时只有 GET 分支 —— 服务端回 200、0 个字段错误，用户看到的就是「按钮点下去没有任何反应」。
实测证据（`django.test.Client`）：`POST /plugins/user/users/?view=new`（空数据）→ 200 且 `ds-field__error` 计数 0；同一份数据 POST 深链 `/users/new/` → 1 个字段错误。考勤规则同理（弹层挂在首页上，POST 落到 `/`）。

**修法**：不写 `action`、改成宿主视图接 POST 并就地渲染回弹层。列表页与独立深链页共用一份正文与一份校验逻辑：
- `plugins/user/views.py`：`_render_user_list(..., edit_user=None)` 升级成「新建 / 编辑」双模式弹层；`user_list` 接 `?view=edit&id=` 与 POST 分派到 `_save_user_create` / `_save_user_edit`（helper 带 `host='list'|'page'`，失败回列表弹层或独立页）。角色同构。
- 新模板 `user/_user_form_body.html`、`user/_role_form_body.html`（create/edit 共用，按钮文案 `{{ user_form_submit }}`）；`user_edit_page.html` / `role_edit_page.html` 为深链 inline 面板。删 `_user_create_body.html` / `_role_create_body.html` / `user_form.html` / `role_form.html`。
- 公告：`notice_list` 接 POST 分派到 `notice_create`；审批：`approval_list` 接 POST 分派到 `approval_create`；考勤规则：抽出 `save_rules(request)`，`attendance_rules` 与首页 `home()`（`panel=attendance&sub=rules`）共用，失败把表单挂到 `request.ds_rules_form` 就地回显。

**本轮铺开的二级页（全部设置面板形态，单分区 → 不列 188px 左栏、内容与按钮居中）**

| 页面 | 形态 | 地址口径 |
|---|---|---|
| 用户管理 / 角色管理 | 列表页 + 列表页上的弹层（新建 / 编辑同壳） | `?view=new`、`?view=edit&id=N` |
| 个人中心 | inline 面板 + 面板上三个弹层（编辑资料 / 查看权限 / 修改密码） | `?view=edit`、`?view=perms`、`?view=password` |
| 公告「已读人员」 | 公告列表 + 弹层（`data-ds-subpage-static`，不跟地址栏同步） | `/notice/<pk>/readers/` |
| 组织架构「用户资料」 | 组织架构页 + 弹层（`_overview_context` 抽出复用；`user_detail.html` 删除） | `/structure/user/<id>/` |
| 审批详情 | inline 面板（wide 720；申请信息 / 流转 / 抄送 / 会签 / 操作五段，操作按钮居中） | `/approval/<id>/` |
| 留痕单条详情 | inline 面板（wide 720，哈希等宽可断行） | `/blockchain/<id>/` |
| 公告发布 / 审批发起 / 模板架构 / 新建用户 / 新建角色 | 沿用 v2.1.3 | 不变 |

**机制补丁**
- `searchHas()` 只取第一组键值（`view=edit&id=7` 原先把 `edit&id=7` 整串拿去比值，编辑弹层永远匹配不上、会被 `sync()` 立刻关掉）。
- `ds_settings_modal.html` 新增 `sp_static`（`data-ds-subpage-static`）：自带地址页的弹层（已读人员、用户资料）由服务端决定开合，`sync()` 跳过它们；✕ / 遮罩 / Escape 关闭照旧。

**真机几何（1440×900，本地 `:8011`，`.tmp-test/screens-v4/`，12 条路由）**
- 个人中心 / 编辑资料 / 权限 / 密码 / 深链编辑页：面板 `800×800`（x=460, y=32）、正文列 `560`、`actions` `560×36` 且 `justify-content=center`、`navRendered=false`。
- 审批详情 `#243`：面板 `800×800`、正文列 `720`、16 行设置行、无左栏。
- 留痕 `#3488`：面板 `800×800`、正文列 `720`、底部按钮居中（`811,682,98,36`）。
- 用户编辑弹层（`?view=edit&id=7`）：遮罩铺满、面板居中、标题「编辑用户：张总」、`gm_zhang` 回填；组织架构用户资料弹层同样服务端即开。

**回归**：全量 `venv/run_tests_shim.py` **511 tests OK**（116s）、`ruff check plugins plugin_host` 全绿；`plugins/structure/tests.py` 的 `基本信息` 断言随行布局改成 `直属上级`（同一覆盖点）。

**考勤三页的收口（用户拍板 ①）**：先核路由，`attendance:attendance_makeup` 是 POST 动作（登记后 302 回 `records/`）、`attendance:attendance_stats` 是 JSON 接口（`?month=` 图表数据源），两者都**不是页面**；真正待统一的只有 `attendance:attendance_records`（签到详情）。取法 ①：保持业务页宽度（明细表 8 列要横向可读），只把表头与卡片密度收回到考勤面板同一套 `at-*` 原语——`at-page`（纵向 16）/ `at-head`（标题 18-26 + 右侧徽标）/ `at-kpis`（四张数卡）/ `at-card` + `at-card__title`（15-22）/ `at-form` + `at-field`（标签 12-16 三级色）/ `at-actions` / `at-note`（12-18 三级色）；内联 `style="font-size:.75rem"` 与 `fs-3`/`fs-5` 全部清掉，`r-btn--plain` 换成 `r-btn--ghost`（§29 的 DSH ghost 取法）。CSS 在第 27 节 `.at-actions` 后追加 `.at-kpis`（`repeat(auto-fit,minmax(180px,1fr))` + `--ds-space-4` 间距）、`.at-kpi`（列向 + 4 间距）、`.at-kpi__label`（12-18 `--ds-label-tertiary`）、`.at-kpi__value`（26-32 `--ds-label-primary` 600 + `tabular-nums`）。

**真机（1440×900，`/plugins/attendance/records/`）**：标题行 + 右侧时间范围徽标、6 项筛选（`at-field` 等宽 flex `1 1 10rem`，筛选/重置在 `at-actions` 换行起排）、四张数卡 180 起、月度看板与签到明细/补卡登记三张卡同 20 padding，明细表表头 10/16。模板测试原断言（`<td>迟到者</td>`、`月度看板`、`attendance-chart`、回退表、`本月暂无考勤记录`）全部保留。

**回归**：`plugins.attendance` 73 tests OK（8.9s）；全量 `venv/run_tests_shim.py` **511 tests OK**（117s）；`ruff check plugins plugin_host` All checks passed。

**容器（v2.1.5 重建）**：`docker compose up -d --build web` 两次（第二次带上多选框封顶）；容器 `constellatio-web-1` Up、gunicorn 3 workers（pid 12/13/14）、`138 static files copied`；本地与容器 MD5 对齐 `attendance_records.html` / `corporate-clean.css` / `ds_settings_modal.html` / `ds-shell.js`，收集后的 `/app/staticfiles/themes/corporate-clean/css/corporate-clean.css` 与源同 hash（`d2a2184a82b5ebe9e45dfcc117935e92`）；容器 25 条路由 GET 全 200（`approval/122`、`notice/14/readers`、`blockchain/1456` 用容器库自身对象；`attendance/stats`、`blockchain/stats` 返回 JSON），截图落 `.tmp-test/screens-v4/container/` 6 张。

**多选框封顶**：`.ds-field select[multiple]` 原为 `min-height:132px` 不封顶，13 个角色会把编辑用户弹层的正文撑到折叠线以下；现加 `max-height:132px; overflow-y:auto`，正文列在 `.ds-settings__options` 内滚动，底部按钮仍可滚到（容器截图 `container/user-edit-modal-light.png` 可见角色框 6 行 + 内部滚动）。
### 9.13.13 业务页内容列：不铺满、紧凑居中（v2.1.5）

用户口径：「这些页面不要铺满，紧凑居中」。取值先按 DSH 会话正文列算（dsh-client-ui-conversation/lib/client.js 的 esolveContentWidth：max(680, min(0.64 * 列宽, 920))），实测 64% 落在 722px 时 8 列签到明细与用户表会折行（部门、姓名竖排），退回该公式的**上限 920**：width: min(920px, 100%) + margin-inline: auto。

落点：	hemes/corporate-clean/templates/base.html 的 .ds-main__body 按 equest.path 前 9 字符是否为 /plugins/ 加 --column；CSS 见主题文件第 31 节，选择器 .ds-main__body--column > :not(.ds-settings)。
- 只收 /plugins/* 业务页；首页（助手 / 看板）保持整屏骨架。
- 根节点就是 .ds-settings 的设置面板页（审批详情、留痕单条、个人中心、新建/编辑深链页）被排除，它们本来就是 800×800 / 720 正文列居中，再套一层会挤。

真机（1440×900）：用户管理 / 组织机构 / 签到详情等内容列 920（x≈399–1319），表头不折行；审批详情仍是 800 面板（x≈460–1260，未受影响）；首页 / 未变。截图 .tmp-test/screens-v5/（本地 8 张 + container/ 4 张）。

**门禁**：全量 env/run_tests_shim.py 511 tests OK（116s）、uff All checks passed；容器重建后 ase.html / corporate-clean.css MD5 与源一致、staticfiles 收集产物 hash dd1447f3eddcfb01ad31c0b5df73b871、gunicorn 3 workers（pid 12/13/14）。

### 9.13.14 留痕链列表回退成原版页面（v2.1.5）

用户口径：「留痕链恢复原来的，查看才是用二级页」。v2.1.3 把留痕链列表整页塞进了 inline 设置面板（标题在面板里、正文列 720），列表页本身并不是"需要切页"的入口，包起来只是缩窄。

- plugins/blockchain/templates/blockchain/blockchain_list.html 回退到 7303c67^ 版本：h2 标题左、共 N 条 徽标右，完整性卡片 + 留痕统计卡片 + 明细表格直排（页宽由业务页 920 列统一收窄）。
- 顺手一处：时间窗口 标签加 	ext-nowrap——920 列下原来被挤成"时间/窗口"两行。
- 「查看」单条（/plugins/blockchain/<id>/）保持设置面板形节：ds-settings--inline ds-settings--single + sp_stack="wide" 720 + 返回留痕链。

### 9.13.15 部门「修改」并入设置二级页（v2.1.5）

用户口径：「部门的修改做成二级页」。v2.1.2 只把「新建」做成了弹层，行内「修改」仍是 POST 回列表后在右侧 col-lg-4 展开一张常驻编辑卡片——同一页面里两套表单形态。

- 视图：`_render_department_page(request, form=None, edit_dept=None, error='', form_open=False)` 升级 create/edit 双模式，产出 dept_form_mode / dept_form_title / dept_form_query / dept_form_url / dept_form_submit；department_list 接 `?view=edit&id=<pk>` 与 POST 分派到 `_save_department_create` / `_save_department_edit`（失败就地渲染回弹层，带上 edit 实例与错误）。
- 模板：新增 user/_department_form.html（共享外壳 includes/ds_settings_modal.html，弹层 id ds-dept-form，sp_query=dept_form_query）与 user/_department_form_body.html（创建/修改共用正文，隐藏 action 随模式切 create/edit）；git rm 掉 _department_new.html / _department_new_body.html；department_list.html 行内「修改」改成 data-ds-modal-open="ds-dept-form" 的链接，右侧常驻编辑卡片整块删除。
- 测试：DepartmentFormPageTests 断言点搬到 ds-dept-form，并补 3 条（编辑深链开弹层且不渲染 col-lg-4、编辑 POST 成功改名并 302、编辑校验失败保持弹层打开且原名不变）。

门禁：全量 514 tests OK（117s）、ruff All checks passed；容器重建后 `?view=edit&id=` 实拍弹层正常（.tmp-test/screens-v6/container/dept-edit.png）。

### 9.13.16 破坏性操作确认框改用 DSH Modal（v2.1.5）

用户口径：「停用 物理删除 禁用 冻结权限的弹窗移植 dsh 的」。这四处的确认一直是原生浏览器灰框（`plugin_host/static/js/confirm.js` 里 `window.confirm`）。

字体/尺寸/间距全部照 DSH 源码字面量：

- 组件本体：`@deepseek-ai/dsh-web-frontend/dist/assets/index-lh_YM6sT.css` 的 Modal 模块 —— `._root_14mp3_6{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:24px}`、`._mask_14mp3_18`、`._dialog_14mp3_33{gap:20px;width:min(380px,100%);padding:0 0 24px;border-radius:var(--dsw-radius-panel);background:var(--dsw-alias-bg-layer-2);box-shadow:var(--dsw-elevation-prominent)}`、`._header_14mp3_71{padding:22px 14px 12px 24px}`、`._title_14mp3_79{16px/24px/500}`、`._close_14mp3_87{28×28}`、`._description_14mp3_108{14px/22px;padding:0 24px}`、`._footer_14mp3_125{justify-content:flex-end;gap:8px}`。
- 确认场景微调：`dsh-client-ui-schedule` 的 `.t-XoWW_confirmDialog{max-height:calc(100dvh - 48px)}`、`.t-XoWW_confirmPrompt{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}`、`.t-XoWW_confirmActions{justify-content:flex-end;gap:8px}`；`Modal` 调用是 `title` + `description` + `footer`（`取消` 带 `data-modal-autofocus`、`确认`），所以本地也把焦点先给「取消」。
- token 映射（唯一差异）：`--dsw-radius-panel`→`--ds-radius-panel`、`--dsw-alias-bg-layer-2`→`--ds-bg-layer-2`、`--dsw-elevation-prominent`→`--ds-elevation-overlay`、`--dsw-alias-bg-mask-1`→`--ds-bg-mask`、`--ds-transition-duration`+`--ds-ease-in-out`→`--ds-dur`+`--ds-ease`。DSH 遮罩另带 `backdrop-filter:var(--dsw-mask-blur)`，本项目无该 token（设置面板遮罩也一直无模糊），故不带模糊，已在 CSS 注释里写明。

落点：

- `themes/corporate-clean/static/themes/corporate-clean/css/corporate-clean.css` 新增第 32 节 `.ds-modal` / `__mask` / `__dialog` / `__content` / `__header` / `__title` / `__close` / `__description` / `__footer` + `@keyframes ds-modal-enter`（`prefers-reduced-motion` 里关动画）。
- `plugin_host/static/js/confirm.js` 重写：仍是 `submit` 捕获 + 三种写法（按钮上 / `<form>` 上 / 表单内任意元素），命中 `data-confirm` 后 `preventDefault()` 再弹 DSH 弹窗；点「确认」用 `form.requestSubmit(submitter)` 复用原提交者（`resubmitting` 标志避免二次拦截）；取消 / 关闭 / 遮罩 / Esc 四路都能退出且不提交。弹窗节点 `role="dialog"` + `aria-modal` + `aria-labelledby`，文案 `textContent` 写入（不走 HTML 解析），高度复用 `.r-btn`。
- 文案可翻译：`themes/corporate-clean/templates/base.html` 新增 `#ds-confirm-labels`（`data-title/data-cancel/data-confirm/data-close`，全部 `{% trans %}`），脚本只读不写死中文；`confirm.js` 链接同时带上 `?v={{ assets_version }}`，`_ASSET_STAMP_FILES` 追加 `plugin_host/static/js/confirm.js`，改脚本也会换版本戳（同名文件缓存问题不再复发）。
- 覆盖的 11 个 `data-confirm` 点（部门停用/物理删除、用户禁用×2/冻结权限、审批删除、结构模板）无需改模板，机制换掉即生效。

门禁：全量 **515 tests OK**（117s），`tests_csp` 相应改口 —— 脚本里 `window.confirm` 必须为 0、钉住 `ds-modal__*` 与 `#ds-confirm-labels`，并新增 `test_confirm_dialog_labels_are_translatable`；真机探针（`.tmp-test/confirm-probe.mjs`）实测部门/用户两页：弹窗 380×186 居中于 1440×900（x=530,y=357）、`取消` 默认聚焦、取消/关闭/Esc 都不提交；`.tmp-test/confirm-submit.mjs` 在临时部门 `zz_probe` 上走完「点停用 → 确认 → 302 回列表」并核到库里 `is_active=False`（探针部门已删）。容器重建后同套实测通过（`.tmp-test/screens-v7/container/`），CSS/JS 的 MD5 与 collected `staticfiles` 一致。

#### 9.13.16.1 修「修改」点成新建页（回归）

用户报「部门的修改怎么是新建的页面」。原因：行内「修改」链接上带着 `data-ds-modal-open="ds-dept-form"`，`ds-shell.js` 命中这个属性就 `preventDefault()` 并就地打开弹层 —— 而列表页预渲染的那块 `#ds-dept-form` 永远是**新建**表单（空白 + 「创建」按钮 + `data-ds-subpage-query="view=new"`），于是点「修改」看到的就是空白新建页。

修法：修改链接去掉 `data-ds-modal-open`，只留 `href="{{ dept_edit_url }}{{ d.id }}"`，走 `?view=edit&id=` 深链由服务端按 edit 渲染（标题「修改部门：X」、`action=edit`、按钮「保存修改」）；新建入口保持不变（它本来就该就地打开预渲染的新建弹层）。用户 / 角色的「编辑」一直是纯链接，所以只有部门这一处跑偏。

顺手修掉同处一个真 bug：那段说明写成多行 `{# … #}`，而 Django 的 `{# #}` **只支持单行**，多行会原样输出到页面（截图里能看到裸文本）。已压成单行，并加 `assertNotIn('{#', html)` 钉住。

测试：`test_row_edit_link_is_deep_link_not_modal_opener` —— 列表页里带 `?view=edit&amp;id=` 的那个 `<a>` 不许出现 `data-ds-modal-open`、列表页预渲染弹层只能是 `action=create`、渲染结果里不许出现 `{#`。真机探针 `.tmp-test/dept-edit-probe.mjs`：点「修改」后 `?view=edit&id=`、标题「修改部门：总裁办/财务部」、`action=edit`、输入框带原名、按钮「保存修改」；点「新建」仍是「新建部门 / create」。全量 516 tests OK。

#### 9.13.17 「留痕链」改名「活动记录」（v2.1.6）

用户口径：「留痕链改名为活动记录」。这是**纯命名**改动，内部标识一律不动：插件名仍是 `blockchain`、模型仍是 `blockchain_record`、URL 仍是 `/plugins/blockchain/`、权限仍是 `blockchain_view` / `blockchain_verify`、动作键仍是 `approval_finished` 这类机器键。改的只是人看到的那层字。

改动点（grep 出的全部用户可见文案）：
- 菜单 label：`plugins/blockchain/apps.py` `menus` 的 `_('留痕链')` → `_('活动记录')`（侧栏、首页「更多」、插件页卡片都吃这一个字符串）。
- 插件 title：同文件 `PluginMeta(title=_('操作留痕链'))` → `_('活动记录')`（记录列表「插件」列的展示名走它）。
- 列表页：`blockchain_list.html` 的 `<title>` 与 `<h2>`（原「操作留痕」/「操作留痕链」）→「活动记录」。
- 详情页：`blockchain_detail.html` 的 `<title>` 与面板标题（`活动记录 #{{ id }}`），`_record_body.html` 底部按钮「返回留痕链」→「返回活动记录」。
- 统计卡片口径随模块名统一：`留痕统计` → `活动统计`、`暂无留痕记录（业务操作会自动上链）` → `暂无活动记录（…）`、`该时间范围内暂无留痕记录` → `该时间范围内暂无活动记录`、`与留痕记录同源` → `与活动记录同源`，charts 插件开关的说明文案同步（「考勤 / 留痕统计图表」→「考勤 / 活动统计图表」）。链完整性相关的「链完整性」「前链哈希」等仍保留链的表述。

翻译：`locale/en/LC_MESSAGES/django.po` 里 `留痕链` 条目改成 `活动记录 / Activity log`，删掉重复的 `操作留痕链` 条目，新增 `返回活动记录 / Back to activity log` 与 `活动记录 #%(id)s / Activity log #%(id)s`（详情页 blocktranslate）。统计卡片那几条 msgid 一并改名并同步 msgstr（`Activity statistics` 等）。

**一个构建链路上的坑（本轮实测发现，未修）**：`.gitignore` 里有 `*.mo`，仓库只存 `.po`；`Dockerfile` / `entrypoint.sh` 都不跑 `compilemessages`，本机也没有 gettext（`msgfmt` / `msguniq` 均不存在）、venv 里没有 babel / polib。也就是说 **`.mo` 既不在版本库、也不在构建期生成**，容器里的 `django.mo` 是靠 Dockerfile 把工作区（含本地 `.mo`）整体拷进镜像带过去的 —— 换台机器 fresh clone 再 build，英文界面会整体回落成中文。本轮为解决这个问题写了个 50 行的纯 Python PO→MO 编译器 `.tmp-test/po2mo.py`（项目外临时物，未入库）：解析 msgid/msgstr + 续行，按 GNU MO 格式重排写出，再用 `gettext.GNUTranslations` 读回校验。若要根治，应把 `.mo` 纳入构建（镜像里装 gettext 并在 `entrypoint.sh` 跑 `manage.py compilemessages -l en`，或把生成好的 `.mo` 收进版本库）。

门禁：新增 `test_menu_label_and_page_title_are_activity_log`（菜单 label 是「活动记录」且不再是「留痕链」、列表页 h2/title、详情返回按钮、三处都不得再出现「留痕链」）与 `test_activity_log_is_translated`（英文列表 `Activity log`、详情 `Activity log #` 与 `Back to activity log`）；`plugin_host/tests_rbac.py` 的菜单守卫断言同步改成断言首页不含「活动记录」。全量 518 tests OK，ruff 通过。

真机（本地 8011 + 容器 8000 各一遍）：侧栏菜单「活动记录」、`<title>` = `活动记录 · Constellatio`、h2 = 活动记录、统计卡 = 活动统计、列表页全文不含「留痕链」；点「查看」进详情，面板标题「活动记录 #3489」、底部「返回活动记录」；切英文为 `Activity log` / `Activity log #` / `Back to activity log`。容器 `django.mo` md5 与本地一致（`425c80fb…`），`blockchain_detail.html` md5 一致（`c63efa7d…`）。

docs 里的 `留痕链` 未回改：`docs/thesis/**`、`plugin-dev-*.md`、`roadmap.md`、`database-design.md` 等是版本史与交付记录，改写历史叙述会让「当时叫什么」失真；本文档从 9.13.17 起用新名字，历史小节保持原样。

### 9.13.18 二级页元素按 DSH 字段模块对齐（v2.1.6）

**用户诉求**：「二级页的元素移植 dsh 的风格，细节方面参考 dsh 源码」（同一要求在此之前重复过一次「看着 dsh 的源码来，别靠猜测」）。

**取证路径**（先取证、后改样式，所有数值都能回到代码行）：
- `dsh-web-frontend/dist/assets/index-lh_YM6sT.css` 里的 `_field_181ew` 模块 —— DSH 设置页的 SettingsValueField 本体（label / head / help / invalid / hint / input 全套）。
- 同一份 dist CSS 的 `_checkbox_1wz3s_1` —— DSH 复选框。
- `dsh-client-ui-settings-general/lib/client.js` 的 `_WvWnq_section` —— 分区末行不画线：`._WvWnq_section>[data-slot="settings.general.item"]>:last-child{border-bottom:none}`。
- 已复核但**不改**的：`.r-btn`（36 / 14-22 / padding 0 14 / radius-md / gap 4）、`.r-input`（34 / 0 12 / .5 border-l4 / radius-md / bg-layer-3 / 13 lh 1.5）原本就与 `_button_1ulci_2` / `_input_181ew_115` 一致，本轮不动。

**我们与源码的三处不一致（旧值 → 源码值）**：

| 元素 | 旧值 | DSH 字面量（`_field_181ew`） |
| --- | --- | --- |
| `.ds-field__label` | `color: --ds-label-secondary`、lh 20px | `flex:1;min-width:0;font-size:13px;font-weight:500;line-height:1.5;color:label-primary` |
| `.ds-field__help` | 12/18、`color: --ds-label-tertiary`、无上内距 | `padding:10px 0 0;font-size:12px;line-height:1.6;color:label-secondary` |
| `.ds-field__error` | 12/18 | `margin:0;font-size:12px;line-height:1.5;color:state-error-primary` |

顺带补两条同源规则：`.r-input/.r-select/.r-textarea[aria-invalid="true"]{border-color:state-error}`（对应 `._input_181ew_115[aria-invalid=true]{border-color:state-error-primary}`）、只读行 `.ds-settings__row` 上下内距 16 → **12**（字段行同为 `padding:12px 0`，一个面板里表单行/只读行节奏一致）、`.ds-fields .ds-settings__row:last-child{border-bottom:none}`（分区末行不画线）、`.ds-settings__row-title` 14/22 → **13 / 500 / 1.5 / label-primary**。

**补一个整块漏移植的类**：`.ds-field__checkbox` 在 `_notice_create_body.html:27`（公告置顶）与 `_template_body.html:16`（授予管理员权限）里被用，但 CSS 里**一条规则都没有**（全站扫描：`plugins/**` 模板里出现却无样式的 `ds-/r-` 类只剩它一个），所以这两处一直渲染成裸 `checkbox`。按 `_checkbox_1wz3s_1` 补齐：

```
inline-flex / align-items:center / gap:6px / font-size:14px / line-height:20px / color:label-primary
input{flex:0 0 auto;width:16px;height:16px;margin:0;accent-color:brand-primary;cursor:inherit}
input:focus-visible{outline:1px solid state-business;outline-offset:2px}
:has(input:disabled){cursor:default;opacity:.5}
```

**落点**：`corporate-clean.css` 第 33 节（文首逐条抄源码字面量，便于以后核对），全部用 `--ds-*` token 写、不再出现裸色值。

**门禁**：`plugin_host/tests.py` 新增 `ThemeDiscoveryTest.test_panel_element_literals_match_dsh` —— 同一选择器在文件里出现多次（第 33 节覆盖旧值），断言取**最后一次**定义，逐条校验 label/help/error/checkbox/只读行/末行不画线，防旧值回潮。全量 tests OK，ruff 通过。

**真机实测（本地 8011，admin，六块面板各一张截图 + 计算样式 dump）**：部门修改（`?view=edit&id=3`）、新建用户（`?view=new`）、发布公告、查看模板、活动记录 #3488、考勤规则。六处 `label` 计算值均为 `rgb(15,17,21) / 13px / 500 / 19.5px`；`help` 均为 `rgb(97,102,107) / 12px / 19.2px / padding-top 10px`；只读行为 `12/12` 内距；公告「置顶」与模板「授予管理员权限」的 checkbox 从裸控件变成 `16×16 / margin 0 / accent-color rgb(15,17,21)`。截图落 `.tmp-test/screens-v9/`（未入库）。

**容器实测（`docker compose up -d --build web` 重建后，8000 端口，容器 admin）**：CSS md5 本地/容器一致（`7143fdaa8cf4fc53f6c2900107516317`），`base.html` 一致（`9e8dcb7aefb17e809d1aa70590a287da`），四块面板（部门修改 / 发布公告 / 活动记录 #1456 / 考勤规则）计算样式与本地逐项相同，公告「置顶」复选框在容器里也是 16×16。截图落 `.tmp-test/screens-v9/container/`。