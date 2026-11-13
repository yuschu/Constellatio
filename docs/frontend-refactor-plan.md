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

*本文不含实现代码；确认后按阶段逐个交付，每阶段单独提交与验收。*
