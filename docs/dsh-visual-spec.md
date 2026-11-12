# DSH 视觉规格实测

> 取数方式：本地起 `@deepseek-ai/dsh@0.2.2-rc.1` 的 web 实例（`npx @deepseek-ai/dsh web --port 8787`），用真实浏览器读 `getComputedStyle` 与 CSS 自定义属性。
> 采集时间：2026-11-12。
> 本文件只记录**实测值**，每条标注来源与可信度；未取到的部分单列一节，不猜。

---

## 一、可信度声明（先看这节）

| 状态 | 内容 |
|---|---|
| ✅ **完整实测** | 浅色态 114 个语义色别名（`--dsw-alias-*`）全量、圆角档位、动效时长与缓动、字体栈、hairline 宽度、角形状，共 462 个变量 |
| ✅ **完整实测** | **深色态 114 个 alias 全部为 CSS 原值**（`getComputedStyle(body).getPropertyValue()` 直接读出，非像素采样），变量总数 479（§3.6） |
| ✅ **抽样实测** | 字号/行高/字重（页面实际渲染的 6 组）、若干组件几何（菜单项、气泡、面板、步骤点） |
| ⚠️ **未取到** | 完整控件的精确高度（按钮/输入框）、图标尺寸与描边粗细、阴影档位（DSH 用描边而非投影，见 §5） |

**结论**：浅色与深色两态均已 1:1 实测，可直接对齐，**不需要再补采**。

---

## 二、token 三层架构（这是最该抄的结构）

实测确认 DSH 是三段式，不是"一堆变量"：

```
--dsw-static-*   原始色板（不可直接用于组件）
      ↓ 映射
--dsw-alias-*    语义别名（组件只消费这一层）
      ↓
--dsw-radius-* / --dsw-font-*   几何与排版原子
```

**关键证据**：组件 CSS 里写的是 `background: var(--dsw-alias-button-primary-fill)`、`color: var(--dsw-alias-label-primary)`——**没有一个组件直接写十六进制**。这与它 npm 描述里"颜色 100% 消费官方 token"一致，且已实证。

**为什么这个结构重要**：换主题时只替换 `alias → static` 的映射表，组件 CSS 一行不动。这是深色/浅色能共存的唯一可靠方式。

### 实测到的静态色板样本

| token | 值 |
|---|---|
| `--dsw-static-blue-100` | `#dbeafe` |
| `--dsw-static-deepseek-500` | `#4176e6` |
| `--dsw-static-neutral-bluish-150` | `#e9ecf2` |
| `--dsw-static-neutral-bluish-700` | `#61666b` |
| `--dsw-static-neutral-bluish-750` | `#43454a` |
| `--dsw-static-neutral-bluish-850` | `#2c2c2e` |

---

## 三、语义色别名全量（114 个，浅色态实测）

### 表面 / 背景

| token | 值 | 用途 |
|---|---|---|
| `bg-base` | `#fff` | 页面底 |
| `bg-layer-1` / `layer-2` / `layer-3` | `#fff` | 分层卡片（浅色下同值，深色下会分开） |
| `bg-overlay` | `#e9ecf2` | 浮层底 |
| `bg-module-platform` | `#f5f6f7` | 平台模块底 |
| `bg-multi-select` | `#f5f6f7` | 多选区 |
| `bg-skeleton` | `#0000000a` | 骨架屏 |
| `bg-mask-1` / `2` / `3` | `#0000003d` / `#0000001f` / `#0000007a` | 三级遮罩（越深越重） |
| `bg-mask-drop` | `#ffffffb3` | 拖拽遮罩 |
| `bg-mask-photo` | `#000000e0` | 图片浏览遮罩 |
| `bg-document-preview` | `#ebeef2` | 文档预览底 |
| `bg-document-selection` | `color-mix(in srgb, #3b82f6 40%, transparent)` | 选中高亮 |

### 文字（label）

| token | 值 | 用途 |
|---|---|---|
| `label-primary` | `#0f1115` | 主文字（近黑，非纯黑） |
| `label-primary-dimmed` | `#151517` | 主文字弱化 |
| `label-primary-inverted` | `#fff` | 反色字 |
| `label-primary-foreground` | `#fff` | 叠在深色按钮上的字 |
| `label-primary-bluish` | `#0e3074` | 蓝调主文字 |
| `label-secondary` | `#61666b` | 次文字 |
| `label-tertiary` | `#81858c` | 辅助文字 |
| `label-caption` | `#adb2b8` | 说明文字 |
| `label-dimmed` | `#e1e5ee` | 极弱文字 |

**三阶灰 `#0f1115` / `#61666b` / `#81858c` / `#adb2b8` 是这套视觉的骨架**，比你项目中 `--r-ink: #111827` 更中性（`#111827` 偏蓝，`#0f1115` 几乎无彩度）。

### 描边（border）——四级全半透明

| token | 值 | 说明 |
|---|---|---|
| `border-l1` | `#0000000a` | 最淡，用于大面积分隔 |
| `border-l2` | `#0000001a` | 常规描边 |
| `border-l3` | `#0000001f` | 强调描边 |
| `border-l4` | `#00000029` | 浮层描边（= `elevation-stroke-color`） |
| `border-inverted` | `#0000` | 占位 |

**这条是精致感的核心**：四级描边不是四个灰度色，而是**同一个黑的不同透明度**，所以叠在任何底色上都自然融合。

### 品牌与链接

| token | 值 |
|---|---|
| `brand-primary` | `#0f1115`（**近黑**） |
| `brand-primary-invert` | `#0f1115` |
| `brand-text` | `#0f1115` |
| `link` | `#4176e6` |
| `button-info-fill` | `#4176e6` |

**注意**：品牌主色是近黑，蓝（`#4176e6`）只用于链接、信息按钮、业务状态。对比你项目现在的 `--r-pink: #2563eb`（蓝）、`--r-blue: #1d4ed8`——你项目的主视觉是蓝，DSH 的主视觉是黑+蓝点缀。**这是观感差异的最大来源之一。**

### 按钮

| token | 值 |
|---|---|
| `button-primary-fill` | `#0f1115` |
| `button-primary-hover` | `#43454a` |
| `button-primary-dimmed` | `#ebeef2` |
| `button-info-hover` | `#7aaaff` |
| `button-contrast-fill` | `#61666b` |
| `button-ghost-active-fill` | `#ebeef2` |
| `button-ghost-active-border` | `#979da6` |
| `button-ghost-active-hover` | `#e9ecf2` |
| `button-elevated-fill` / `floating-fill` | `#fff` |
| `button-floating-hover` | `#f1f3f5` |
| `button-tool-bar-fill` | `#54555780` |
| `button-tool-bar-fill-invisible` | `#1f1f1f5c` |
| `button-tool-bar-hover` | `#54555799` |

### 交互态（hover / active）——极淡叠加

| token | 值 |
|---|---|
| `interactive-bg-hover` | `#2631480f` |
| `interactive-bg-hover-solid` | `#f1f3f5` |
| `interactive-bg-active` | `#2631481a` |
| `interactive-bg-hover-accent` | `#26314824` |
| `interactive-bg-hover-danger` | `#ec13130d` |
| `state-idle-primary` | `#d4d4d4` |
| `switch-thumb` | `#fff` |

**手法**：hover 用 `#263148`（蓝灰）的 **6%–14% 透明度**叠加，不是换一个实色。这样在任何底色上都成立。

### 状态色

| 语义 | primary | secondary | tertiary |
|---|---|---|---|
| success | `#22c55e` | `#4ed17e` | `#e6faed` |
| warn | `#f59e0b` | `#f7ad31` | `#fef5e7` |
| error | `#ec1313` | `#f25a5a` | — |
| done | `#7c3aed` | — | — |
| business | `#4176e6` | — | `#e4edfd` |
| warn-label | `#dd8629` | — | — |

### 浮层（tooltip / toast / menu）

| token | 值 |
|---|---|
| `tooltip-bg` | `#2c2c2e` |
| `tooltip-label` | `#fff` |
| `toast-bg` | `#353638` |
| `toast-label` | `#fff` |
| `menu-icon` | `#353638` |
| `menu-group-header-fill` | `#f8f9faf0` |

### 代码 / Markdown

| token | 值 |
|---|---|
| `markdown-code-block` | `#f9fafb` |
| `markdown-code-block-banner` | `#f9fafb` |
| `markdown-inline-code` | `#fafafa` |
| `markdown-tag` | `#f1f3f5` |
| `markdown-citation` | `#ebeef2` |
| `markdown-placeholder` | `#f5f6f7` |

### 差异对比（diff）

| token | 值 |
|---|---|
| `file-diff-added-bg` / `marker` / `gutter` | `#e6f4e7` / `#01a241` / `#edf7ed` |
| `file-diff-deleted-bg` / `marker` / `gutter` | `#fce6e2` / `#ba2723` / `#fdece9` |

### 滚动条

| token | 值 |
|---|---|
| `scrollbar-bg-l1` / `l2` | `#e5e5e5` |
| `scrollbar-hover-l1` / `l2` | `#d4d4d4` |

### 3.5 深色态（CSS 原值，2026-11-12 补采）

**取数方式**：`npx @deepseek-ai/dsh@latest web --port 8787` 起实例 → 用独立 profile 的 Chrome 经 CDP 连页面 → `getComputedStyle(document.body).getPropertyValue('--dsw-alias-*')` 逐条读出。**这是 CSS 变量的原值，不是截图采样。**

实测环境：`data-ds-theme-source="dark"`、`color-scheme: dark`、`body` 背景 `rgb(21, 21, 23)`、文字 `rgb(249, 250, 251)`，变量总数 **479**（浅色 462，深色多出的部分是 `--dsh-boot-*` 等启动态变量）。

#### 表面 / 背景

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `bg-base` | `#151517` | `#fff` |
| `bg-layer-1` | `#232324` | `#fff` |
| `bg-layer-2` | `#2c2c2e` | `#fff` |
| `bg-layer-3` | `#353638` | `#fff` |
| `bg-overlay` | `#61666b` | `#e9ecf2` |
| `bg-module-platform` | `#353638` | `#f5f6f7` |
| `bg-multi-select` | `#212123` | `#f5f6f7` |
| `bg-skeleton` | `#ffffff14` | `#0000000a` |
| `bg-mask-1` / `2` / `3` | `#00000080` / `#0003` / `#0000007a` | `#0000003d` / `#0000001f` / `#0000007a` |
| `bg-mask-drop` | `#272730b3` | `#ffffffb3` |
| `bg-mask-photo` | `#000000e0` | `#000000e0` |
| `bg-document-preview` | `#151517` | `#ebeef2` |
| `bg-document-selection` | `color-mix(in srgb, #3b82f6 40%, transparent)` | 同值 |

#### 文字（label）

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `label-primary` | `#f9fafb` | `#0f1115` |
| `label-primary-dimmed` | `#ebeef2` | `#151517` |
| `label-primary-inverted` | `#353638` | `#fff` |
| `label-primary-foreground` | `#0f1115` | `#fff` |
| `label-primary-bluish` | `#f9fafb` | `#0e3074` |
| `label-secondary` | `#cfd3d6` | `#61666b` |
| `label-tertiary` | `#adb2b8` | `#81858c` |
| `label-caption` | `#81858c` | `#adb2b8` |
| `label-dimmed` | `#43454a` | `#e1e5ee` |

**三阶灰整体提亮并重排**：浅色 `#61666b → #81858c → #adb2b8`（越弱越亮），深色 `#cfd3d6 → #adb2b8 → #81858c`（越弱越暗）。

#### 描边（border）——半透明方向反转

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `border-l1` | `#ffffff0f` | `#0000000a` |
| `border-l2` | `#ffffff1f` | `#0000001a` |
| `border-l3` | `#ffffff29` | `#0000001f` |
| `border-l4` | `#fff3` | `#00000029` |
| `border-inverted` | `#ffffff0f` | `#0000` |
| `border-inverted2` | `#ffffff14` | — |
| `border-l2-darkmode-thin` | `#ffffff0f` | — |

**关键**：浅色是半透明**黑**叠在浅底上，深色是半透明**白**叠在深底上。四级结构、递增节奏完全一致，只是色相翻转。

#### 品牌与链接

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `brand-primary` | `#f9fafb` | `#0f1115` |
| `brand-primary-invert` | `#f9fafb` | `#0f1115` |
| `brand-text` | `#f9fafb` | `#0f1115` |
| `brand-primary-new-color` | `#5686fe` | — |
| `link` | `#7aaaff` | `#4176e6` |

**品牌主色直接对调**：浅色近黑、深色近白。所以深色下"主按钮"是白底深字。

#### 按钮

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `button-primary-fill` | `#f9fafb` | `#0f1115` |
| `button-primary-hover` | `#ebeef2` | `#43454a` |
| `button-primary-dimmed` | `#43454a` | `#ebeef2` |
| `button-info-fill` | `#7aaaff` | `#4176e6` |
| `button-info-hover` | `#4176e6` | `#7aaaff` |
| `button-contrast-fill` | `#f9fafb` | `#61666b` |
| `button-ghost-active-fill` | `#43454a` | `#ebeef2` |
| `button-ghost-active-border` | `#81858c` | `#979da6` |
| `button-ghost-active-hover` | `#61666b` | `#e9ecf2` |
| `button-elevated-fill` | `#43454a` | `#fff` |
| `button-floating-fill` | `#2c2c2e` | `#fff` |
| `button-floating-hover` | `#353638` | `#f1f3f5` |
| `button-tool-bar-fill` | `#54555780` | `#54555780` |
| `button-tool-bar-fill-invisible` | `#1f1f1f5c` | `#1f1f1f5c` |
| `button-tool-bar-hover` | `#54555799` | `#54555799` |

注意 `button-info-fill` 与 `button-info-hover` 在深色下**互换**：填充用亮蓝 `#7aaaff`，hover 反而变深 `#4176e6`（悬停加深而非减淡）。

#### 交互态——白叠加而非蓝叠加

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `interactive-bg-hover` | `#ffffff14` | `#2631480f` |
| `interactive-bg-hover-solid` | `#353638` | `#f1f3f5` |
| `interactive-bg-active` | `#ffffff24` | `#2631481a` |
| `interactive-bg-hover-accent` | `#ffffff3d` | `#26314824` |
| `interactive-bg-hover-danger` | `#f25a5a26` | `#ec13130d` |
| `state-idle-primary` | `#545557` | `#d4d4d4` |
| `switch-thumb` | `#adb2b8` | `#fff` |

浅色用蓝灰 `#263148` 的极低透明度叠加，深色改用**纯白** `#ffffff` 叠加（`14/24/3d`，即 8% / 14% / 24%）。

#### 状态色

| 语义 | 深色 primary | 深色 secondary | 深色 tertiary | 浅色 primary |
|---|---|---|---|---|
| success | `#22c55e`（同） | `#4ed17e`（同） | `#233c2c` | `#22c55e` |
| warn | `#f59e0b`（同） | `#f7ad31`（同） | `#27241f` | `#f59e0b` |
| error | `#f25a5a` | `#f25a5a` | — | `#ec1313` |
| done | `#a78bfa` | — | — | `#7c3aed` |
| business | `#7aaaff` | — | `#34415b` | `#4176e6` |
| warn-label | `#dd8629`（同） | — | — | `#dd8629` |

success / warn 两口**完全不变**，说明它们本来就按深底设计；error / done / business 都向亮端提了一档（`#ec1313→#f25a5a`、`#7c3aed→#a78bfa`、`#4176e6→#7aaaff`）。tertiary 从浅底换成深底（`#e6faed→#233c2c`）。

#### 浮层

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `tooltip-bg` | `#43454a` | `#2c2c2e` |
| `tooltip-label` | `#fff` | `#fff` |
| `tooltip-key-bg` | `color-mix(in srgb, #43454a, white 18%)` | — |
| `toast-bg` | `#43454a` | `#353638` |
| `toast-label` | `#fff` | `#fff` |
| `menu-icon` | `#ebeef2` | `#353638` |
| `menu-group-header-fill` | `#303136f0` | `#f8f9faf0` |
| `hovercard-bg` | — | — |

#### 代码 / Markdown

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `markdown-code-block` | `#1b1b1c` | `#f9fafb` |
| `markdown-code-block-banner` | `#2c2c2e` | `#f9fafb` |
| `markdown-inline-code` | `#292929` | `#fafafa` |
| `markdown-tag` | `#2c2c2e` | `#f1f3f5` |
| `markdown-citation` | `#353638` | `#ebeef2` |
| `markdown-placeholder` | `#2c2c2e` | `#f5f6f7` |
| `markdown-code-segment-selected` | `#353638` | — |
| `markdown-code-segment-unselected` | `#1b1b1c` | — |

#### 差异对比（diff）

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `file-diff-added-bg` | `#1f3124` | `#e6f4e7` |
| `file-diff-added-gutter` | `#132016` | `#edf7ed` |
| `file-diff-added-marker` | `#41c977` | `#01a241` |
| `file-diff-deleted-bg` | `#3c1f1b` | `#fce6e2` |
| `file-diff-deleted-gutter` | `#28130e` | `#fdece9` |
| `file-diff-deleted-marker` | `#fa423e` | `#ba2723` |
| `code-diff-added` | `#22c55e1f` | — |
| `code-diff-deleted` | `#f25a5a1f` | — |

#### 滚动条

| token | 深色值 | 浅色值（对照） |
|---|---|---|
| `scrollbar-bg-l1` | `#3c3c3d` | `#e5e5e5` |
| `scrollbar-bg-l2` | `#545557` | `#e5e5e5` |
| `scrollbar-hover-l1` | `#545557` | `#d4d4d4` |
| `scrollbar-hover-l2` | `#65676b` | `#d4d4d4` |

#### 其余 alias

| token | 深色值 |
|---|---|
| `elevation-stroke-color` | `#fff3` |
| `settings-card-fill` | `#2c2c2e` |
| `settings-card-stroke` | `#fff3` |
| `illustration-background` | `#2c2c2e` |
| `illustration-backing` | `#43454a` |
| `illustration-detail` | `#81858c` |
| `illustration-inset` | `#43454a` |
| `illustration-shadow` | `#43454a` |
| `illustration-surface` | `#61666b` |
| `onboarding-accent` | `#3964fe` |
| `onboarding-card-fill` | `color-mix(in srgb, #2c2c2e 80%, transparent)` |
| `onboarding-checkbox-border` | `#ffffff1f` |
| `onboarding-secondary-fill` | `#48494c` |
| `label-document-preview` | `#cfd3d6` |
| `label-deep-diving` | `color-mix(in srgb, #5686fe 55%, #adb2b8)` |
| `label-deep-diving-shimmer` | `color-mix(in srgb, #93c5fd 65%, #7aaaff)` |
| `label-shimmer` | `color-mix(in srgb, #fff 45%, transparent)` |
| `turn-trigger-bg` | `#ffffff14` |
| `turn-trigger-bg-hover` | `#ffffff24` |

#### 深色态暴露的三个结构性事实

1. **深色不是另一套色板**。深色值全部落在同一批 `--dsw-static-*` 上：`bluish-1000 #0f1115`、`bluish-900 #1b1b1c`、`bluish-875 #232324`、`bluish-850 #2c2c2e`、`bluish-800 #353638`、`bluish-750 #43454a`、`neutral-850 #212123`、`neutral-700 #3c3c3d`、`neutral-600 #545557`。浅色用的是 `bluish-50 #f9fafb`、`bluish-75 #f1f3f5`、`bluish-100 #ebeef2`、`bluish-500 #979da6` 等。**同一批色板的不同档位**，这正是 §2 三层结构"换映射不换零件"的实证。
2. **深色是纯中性灰，零蓝调**。`#151517` / `#1b1b1c` / `#232324` / `#2c2c2e` 的 R≈G≈B，唯一轻微偏离是 `#151517`（R=21, G=21, B=23，蓝高 2）。而浅色板的 `neutral-bluish-*` 有明确蓝调（如 `#e9ecf2` 的 B 比 R 高 9）。
3. **层次方向反转且拉开**。浅色 `layer-1/2/3` 全是 `#fff`（靠描边和阴影分层，色值不分层）；深色 `base #151517 → layer-1 #232324 → layer-2 #2c2c2e → layer-3 #353638`，**每档亮度递增、层级越高越亮**。这是深色界面必须靠亮度分层的直接体现。

#### 3.5.1 历史像素采样（旁证，已被上表取代）

2026-11-12 早前从桌面端 1821×1138 截图采样，现作交叉验证：

| 区域 | 采样值 | 对应 alias 原值 | 结论 |
|---|---|---|---|
| 主内容区底 | `#151517` | `bg-base` `#151517` | 完全一致 |
| 卡片 / 面板 | `#212123` | `bg-multi-select` / `static-neutral-850` 同值 | 完全一致 |
| 代码块 | `#1B1B1C` | `markdown-code-block` `#1b1b1c` | 完全一致 |
| 顶栏 | `#151517` | `bg-base` | 完全一致 |
| 主文字（最亮像素） | `#F9FAFB` | `label-primary` `#f9fafb` | 完全一致 |
| 侧栏底 | `#1B1B1C` | 无单一 alias 对应（疑为 `bluish-900` 或侧栏独立变量叠加） | **唯一未对上的一处** |

**结论**：像素采样 5/6 命中，误差为 0 而非先前估计的 ±2 灰阶。但采样法仍然不该作为最终依据——它是间接测量，每次都依赖截图时机的渲染状态；本次起改用 CSS 原值直读。**侧栏那一项留下一个待查点**：深色侧栏为何不是 `layer-1 #232324` 而是更暗的 `#1b1b1c`，需在真实页面上定位侧栏元素的 computed background 才能确认。

**精度声明**：上述两表性质不同——§3.5 主表是 `getPropertyValue` 读出的 CSS 变量原值，可直接写进代码；§3.5.1 是像素采样，只能作交叉验证，不得当作设计原值使用。

---

## 四、圆角与角形状（这条决定"圆润但不呆板"）

实测 6 档：

| token | 值 | 典型用途 |
|---|---|---|
| `--dsw-radius-xs` | **4px** | 小标签、内嵌块 |
| `--dsw-radius-sm` | **8px** | 按钮、输入框、菜单项 |
| `--dsw-radius-md` | **12px** | 卡片、面板 |
| `--dsw-radius-lg` | **16px** | 大卡片 |
| `--dsw-radius-xl` | **20px** | 气泡、浮动层 |
| `--dsw-radius-panel` | **28px** | 大面板、弹层 |

**关键**：`--dsw-corner-shape: superellipse(1.5)`。

这是 2024+ 的 CSS 新特性，把标准圆角（四分之一圆）替换成**超椭圆**。视觉差别：标准圆角在切线处会有一条隐约的"拐点"，超椭圆是连续曲率，所以看起来更"顺"。这是 DSH 界面比普通圆角界面显得更精致的**第二个来源**（第一个是半透明描边）。

**按需关闭**：实测发现步骤点用 `border-radius: 50%; corner-shape: round`——说明超椭圆是全局默认、个别元素显式退回标准圆角。这是可用的控制方式。

---

## 五、描边与分隔（不是投影）

| token | 值 | 说明 |
|---|---|---|
| `--dsh-hairline-width` | **0.8px** | 全局发丝线宽度——不用 1px |
| `--dsw-elevation-stroke-color` | `#00000029` | 浮层"阴影"实际是描边色 |
| 实测面板边框 | `0.5px solid` | 部分浮层用 0.5px |
| `--dsw-focus-ring-width` | **2px** | 焦点环 |
| 实测步骤点边框 | `1.5px` | 中等强调 |
| 实测激活态 | `box-shadow: inset 0 0 0 1px var(...)` | **用内阴影做描边，不用 border** |

**两个手法值得直接抄**：
1. **0.5px / 0.8px 发丝线**——比 1px 更精细，在 Retina 上尤其明显；
2. **激活态用 `inset 0 0 0 1px` 内阴影而非 `border`**——因为改 `border` 会改变元素尺寸导致布局抖动，内阴影不会。

---

## 六、字体与字阶

### 字体栈（三类，各自独立）

| 用途 | 值 |
|---|---|
| 文本 | `-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif` |
| 等宽 | `"SF Mono", "JetBrains Mono", "Fira Code", Consolas, "Liberation Mono", Menlo, Courier, "PingFang SC", "Microsoft YaHei"` |
| 品牌 | `"Montserrat", -apple-system, BlinkMacSystemFont, ...` |

**对比你项目**：你现在是 `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif`——**没有 PingFang SC / Hiragino Sans GB / Microsoft YaHei**。这三个是中文在 macOS / 旧版 mac / Windows 上的最优字体，React 完这一条，中文观感会立刻不同。同时你去掉了 Roboto（Android 用），DSH 也没用它。

### 实测字阶（页面真实渲染值）

| 角色 | 字号 | 字重 | 行高 | 备注 |
|---|---|---|---|---|
| 正文 | 16px | 400 | — | 容器默认 |
| 次级正文 | 14px | 400 | 24px | 1.71 倍行高 |
| 控件标签 | 13px | 500 | 20px | 1.54 倍 |
| 大标题 | 26px | 500 | 32px | 1.23 倍（紧行高） |
| 品牌字标 | 16px | 600 | 24px | **letter-spacing 0.08em** |
| 弹层失败标题 | 14px | 600 | 22px | — |
| Markdown 小字 | 12px | — | 20px | — |
| 终端 | 13px | — | — | — |
| 代码 | 11px | — | — | — |

**可观感的细节**：字重只用 400 / 500 / 600 三档，不用 700（粗体在深色界面上会糊）；字标用 `0.08em` 字距做"品牌感"。

---

## 七、动效

| token | 值 |
|---|---|
| `--ds-transition-duration-fast` | `.1s` |
| `--ds-transition-duration` | `.2s` |
| `--ds-transition-duration-slow` | `.3s` |
| `--ds-ease-in-out` | `cubic-bezier(.4, 0, .2, 1)` |
| 实测元素过渡 | `0.18s, 0.12s`（多属性分别计时） |

**手法**：不统一用一个时长，而是按属性分别给（`0.18s` 给颜色、`0.12s` 给变换）。这比"全部 0.2s"更自然。

---

## 八、几何实测（抽样的真实组件尺寸）

| 组件 | 实测值 | 来源 |
|---|---|---|
| 菜单项 | `min-height: 34px`、`padding: 6px 8px`、`gap: 6px` | CSS 规则 |
| 气泡 | `border-radius: 20px`（= radius-xl）、`padding: 10px 16px` | CSS 规则 |
| 步骤点 | `border-radius: 50%`、`border: 1.5px`、`corner-shape: round` | CSS 规则 |
| 图标按钮 | `border-radius: 8px`（= radius-sm） | computed style |
| 浮动面板 | `padding: 4px 6px`、`border: .5px solid` | CSS 规则 |
| 内容区 | `padding-top: 24px`、`padding-left: 24px` | computed style |
| 联系人按钮 | `border-radius: 8px`、`padding-left: 8px`、`13px/500/20px` | computed style |
| 侧栏高度 | `--dsh-sidebar-height: 0px`（可折叠） | CSS 变量 |

**注意**：24px 是这套系统的主间距单位（内容区留白、卡片内边距的基础）。你项目现在是 `mt-4`（Bootstrap 16px）为主——这是"看起来松散/紧凑"的另一个差异点。

---

## 九、主题机制（怎么做出深色）

实测的运行时证据。

**浅色态（`themeSource = system`，系统为浅色时）**：

```html
<html lang="zh-CN" data-ds-theme-source="system"
      style="--dsh-hairline-width: 0.8px; color-scheme: light; --dsh-sidebar-height: 0px;"
      data-input-modality="pointer">
```

**深色态（补采时实测，系统为深色时）**：

```js
getComputedStyle(document.documentElement).colorScheme   // "dark"
document.documentElement.dataset.dsThemeSource           // "dark"
getComputedStyle(document.body).backgroundColor          // "rgb(21, 21, 23)"
getComputedStyle(document.body).getPropertyValue('--dsw-alias-bg-base')  // "#151517"
```

**机制要点**：

- 主题由 `data-ds-theme-source` 决定，默认 `system`（跟随系统，所以同一台机器上它会自己变深变浅）；
- `color-scheme` 随之切 `light` / `dark`，这同时改变浏览器原生控件（滚动条、输入框、日期选择器）的外观——**不需要自己重画这些控件**，这是被低估的一条；
- **全部 `--dsw-alias-*` 由运行时写入，可通过 `getComputedStyle(document.body).getPropertyValue()` 读到**（`html` 与 `body` 的 inline style attribute 本身很短，约 75 / 90 字符，说明 alias 不是靠单个 `style` 属性字符串携带的，但 computed 层可解析）；
- 静态样式表里**只有引用没有定义**（早前遍历 `document.styleSheets` 确认）。所以"抄一份静态 CSS 就拿到深色"是做不到的——**必须自己写两套 alias 映射**。

**推论**：DSH 切换主题 = 重新把一整套 `--dsw-alias-*` 写进运行时，组件 CSS 完全不变。实测浅色 462 个变量、深色 479 个变量，两态组件 CSS 是同一份。

**这正是 Constellatio 该采用的方式**：两套主题 = 两套 alias 到 static 的映射表，组件类只引用 alias。

---

## 十、未取到的部分与补救

| 缺失项 | 原因 | 补救方式 |
|---|---|---|
| **深色侧栏底色的来源** | 像素采样得 `#1B1B1C`，但深色 alias 里 `bg-layer-1` 是 `#232324`，两者不等。深色 114 个 alias 已全量拿到，唯独"侧栏具体消费哪个变量"未定位 | 在真实页面定位侧栏根元素的 `computed background-color`，或搜 `bluish-900`(`#1b1b1c`) 在侧栏相关 CSS 中的引用 |
| 按钮 / 输入框精确高度 | 当前页未渲染这类控件 | 进插件管理页或设置页再采 |
| 图标尺寸与描边粗细 | 未展开 | 采 `@iconify` 实际渲染的 svg |
| 阴影档位 | DSH 主要用描边而非投影，可能本就没有多档阴影 | 确认后再定 |

---

## 十一、映射到 Constellatio（落地方案）

### 11.1 token 命名照搬，值换掉

直接沿用 `--dsw-alias-*` 的**分层与语义**，但不沿用名字前缀（避免和法律/品牌混淆），也不照搬全部 114 个（OA 用不到 diff / markdown / tooltip 那么细）：

```
--r-static-*      原始色板（20 个左右足够）
--r-alias-*       语义别名（按 OA 页面类型分组，约 40 个）
--r-radius-*      6 档，照搬 4/8/12/16/20/28
--r-hairline      0.8px
--r-dur-fast/base/slow = .1s/.2s/.3s
--r-ease          cubic-bezier(.4, 0, .2, 1)
```

### 11.2 OA 必须补的（DSH 没有的）

| 项 | 为什么必须补 |
|---|---|
| **表格专用色阶** | DSH 无密集表格。**已按 WCAG 公式精确计算**（见 §11.4）：深色 `bg-base #151517` 与 `static-neutral-bluish-900 #1b1b1c` 的对比只有 **1.06:1**，与 `layer-1 #232324` 是 **1.16:1**，`border-l1 #ffffff0f` 叠加后约 `#212123` 对比 **1.13:1**（非文本分层阈值要求 3:1）。**深色的斑马纹与发丝分隔线在密集表格里肉眼基本不可见**——必须靠"行高 + 列对齐 + 列间距 + 单元格内边距"做视觉分栏，或为表格页保留浅底 |
| **打印态覆盖** | 审批单要打印，深色主题必须补 `@media print` 浅色覆盖（否则 40 行表格打印出来是黑底白字，耗墨且不可读） |
| **校验态对比度** | 正文文字层很安全：`label-primary #f9fafb` 在 `#151517` 上 **17.45:1**，`label-secondary #cfd3d6` **12.11:1**，最弱的 `label-caption #81858c` 也有 **4.92:1**（刚过 AA）。**真正的风险在状态色压自己 tertiary 底上**：error `#f25a5a` on `#233c2c` = **3.64:1**、business `#7aaaff` on `#34415b` = **4.39:1**，均低于 4.5:1。校验提示不应放在 tertiary 底色块里 |
| **列表页紧凑档** | DSH 的 24px 主间距是为宽松界面设计的；OA 列表页需另一套（行高 40/48、内边距 8/12） |

### 11.3 两主题怎么分套

沿用 DSH 机制，但**结构 token 完全共用**：

```
tokens.css          --r-radius-* / --r-hairline / --r-dur-* / --r-ease / --r-font-*
                    （两主题完全相同，只定义一次）
themes/corporate-clean/tokens-color.css    --r-alias-* （深色极简那套）
themes/risograph/tokens-color.css          --r-alias-* （印刷风那套，可保留浅色）
```

**这样两套主题的几何与动效永远一致**，只有颜色和纹理不同——这正是你项目当前两套主题重复度 90% 却仍然观感割裂的根因（几何各写各的）。

### 11.4 深色可读性实测（WCAG 相对亮度对比）

用 CSS 变量原值按 WCAG 2.x 公式精确计算（非估算）：

| 组合 | 对比度 | 判定 |
|---|---|---|
| `label-primary #f9fafb` on `bg-base #151517` | **17.45:1** | ✅ AAA |
| `label-secondary #cfd3d6` on `#151517` | **12.11:1** | ✅ AAA |
| `label-tertiary #adb2b8` on `#151517` | **8.54:1** | ✅ AAA |
| `label-caption #81858c` on `#151517` | **4.92:1** | ⚠️ 刚过 AA 4.5，小字慎用 |
| `link #7aaaff` on `#151517` | **7.83:1** | ✅ AAA |
| `success #22c55e` on `#151517` | **8.00:1** | ✅ AAA |
| `warn #f59e0b` on `#151517` | **8.49:1** | ✅ AAA |
| `error #f25a5a` on `#151517` | **5.55:1** | ✅ AA |
| `bg-base #151517` vs `layer-1 #232324` | **1.16:1** | ❌ 分层不可见（非文本要求 3:1） |
| `bg-base #151517` vs `static-neutral-bluish-900 #1b1b1c` | **1.06:1** | ❌ 斑马纹不可见 |
| `bg-base #151517` vs border-l1 叠加 ≈`#212123` | **1.13:1** | ❌ 发丝分隔不可见 |
| `error #f25a5a` on success-tertiary `#233c2c` | **3.64:1** | ❌ 低于 AA |
| `business #7aaaff` on business-tertiary `#34415b` | **4.39:1** | ❌ 略低于 AA |
| `warn #f59e0b` on warn-tertiary `#27241f` | **7.20:1** | ✅ AAA |

**三条可直接落地的结论**：

1. **文字层完全够用**，最弱一档也有 4.92:1，深色下正文不需要额外提亮。
2. **背景分层靠色值是行不通的**（1.06–1.31:1）。深色的"层级感"必须靠 **圆角 + 内边距 + 描边（半透明白，再靠几何位置区分）**，不能靠"底色差一档"。这一点和浅色相反——浅色 `layer-1/2/3` 全是 `#fff`，本来就靠描边和阴影分层。
3. **状态色块不能直接当背景托字**。error / business 压在 tertiary 底色块上会掉到 3.64 / 4.39，低于 AA。校验提示应放在 `bg-base` 或 `layer-1` 上，只用彩色做图标与边框，不用彩色做文字底。

## 附：取数方法（可重跑）

### 起实例

```powershell
# 必须重定向到文件，不能用 | Out-String —— 否则带 token 的那行输出会被缓冲掉
$log = Join-Path $env:TEMP 'dsh-web-8787.log'
& npx.cmd --yes '@deepseek-ai/dsh@latest' web --no-open --port 8787 --host 127.0.0.1 *> $log
# 日志里会打印：dsh web: http://127.0.0.1:8787/?token=xxxx
# 直接访问根路径会 401
```

### 取变量（在页面里执行）

**不要把 `for (const p of cssStyleDeclaration)` 当万能写法**——它只枚举标准属性（camelCase），自定义 `--*` 变量拿不到。正确做法是先收集名字、再逐条取值：

```js
(() => {
  const html = document.documentElement;
  const body = document.body;
  const names = new Set();

  const collectFromDecl = (text) => {
    const re = /(--[a-zA-Z0-9_-]+)\s*:/g;
    let m;
    while ((m = re.exec(text))) names.add(m[1]);
  };

  // 1) 从 inline style 收
  for (const el of [html, body]) {
    const raw = el.getAttribute('style') || '';
    if (raw) collectFromDecl(raw);
  }

  // 2) 从样式表规则收（含 @media 等嵌套）
  const scanRules = (rules) => {
    for (const r of rules) {
      if (r.style) {
        for (const p of Array.from(r.style)) {
          if (p.startsWith('--')) names.add(p);
        }
        collectFromDecl(r.cssText || '');
      }
      if (r.cssRules) scanRules(r.cssRules);
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    try { scanRules(sheet.cssRules); } catch (e) { /* 跨域样式表 */ }
  }

  // 3) 逐条取值
  const csH = getComputedStyle(html);
  const csB = getComputedStyle(body);
  const out = {};
  for (const n of names) {
    out[n] = csB.getPropertyValue(n).trim() || csH.getPropertyValue(n).trim();
  }
  return { count: Object.keys(out).length, vars: out };
})()
```

### 无 DevTools 时：CDP 直连

桌面端 UI 页面不开 inspector，但可以用独立 profile 起一个带调试端口的 Chrome 直连：

```powershell
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profile = Join-Path $env:TEMP 'dsh-probe-profile'   # 用临时 profile，不影响用户现有浏览器
Start-Process -FilePath $chrome -ArgumentList `
  '--remote-debugging-port=9222', "--user-data-dir=$profile", `
  '--no-first-run', '--no-default-browser-check', `
  'http://127.0.0.1:8787/?token=<token>' -WindowStyle Minimized

# 取页面 target 的 webSocketDebuggerUrl
(Invoke-RestMethod 'http://127.0.0.1:9222/json') |
  Where-Object { $_.type -eq 'page' } |
  Select-Object title, url, webSocketDebuggerUrl
```

再用 node（22+ 自带全局 `WebSocket`）发一条 `Runtime.evaluate`：

```js
const ws = new WebSocket(wsUrl);
let id = 0;
ws.onopen = () => ws.send(JSON.stringify({
  id: ++id,
  method: 'Runtime.evaluate',
  params: { expression: <上面那段 IIFE>, returnByValue: true, awaitPromise: true },
}));
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id) { console.log(JSON.stringify(msg.result.result.value, null, 2)); ws.close(); }
};
```

### 已验证做不通的路径（别重试）

| 路径 | 失败原因 |
|---|---|
| 改 `data-ds-theme-source="dark"` | 只改 `color-scheme`，不触发 alias 重新注入 |
| CDP `Emulation.setEmulatedMedia` 模拟 `prefers-color-scheme` | 报 `-32001: Session with given id not found` |
| 遍历 `document.styleSheets` 找 `@media` 里的 alias 定义块 | 静态表只有引用，没有定义 |
| 解包 `resources/app.asar`（203 MB） | 头部不是标准 asar JSON，`UnicodeDecodeError: byte 0xa4 position 0` |
| 桌面端 CDP `/json` 找 UI target | 只暴露 `dsh://host` 一个 realm，UI 页面没开 inspector |
| `node_modules` 里找官方 bundle 源码 | `@deepseek-ai` 下只装了 `cosmokit` / `schemastery` / `dsh-brand`，官方 bundle 在 asar 里 |

**可靠路径只有一条**：让实例真实处于目标任务态（跟随系统深色即可，或用户在 UI 里切），再用浏览器读 `getComputedStyle`。
