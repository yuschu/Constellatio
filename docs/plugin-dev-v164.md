# 插件开发文档：v1.6.4 顶部导航栏吸顶

> 关联：themes（Corporate Clean / Risograph 外壳导航）
> 版本：v1.6.4 · 文档日期：2026-10-23
> 状态：**✅ 已实现并部署**（按要求未执行自动化测试，功能验证交由负责人）

## 一、需求

页面顶部导航栏（品牌 Constellatio + 语言切换 + admin / 登出这一整行）**固定悬浮**：页面向下滚动时，导航栏保持在视口顶部不动。与 v1.6.3 的左侧栏 sticky 相互独立。

## 二、设计口径

| 项 | 决策 |
|---|---|
| 目标元素 | 两套主题 `base.html` 中的 `<nav class="r-nav py-2">`（整行外壳 header） |
| 实现 | 主题 CSS：`.r-nav { position: sticky; top: 0; z-index: 1030; }` |
| 主题适配 | Corporate Clean：白底 + 下边框/浅阴影已有，吸顶后内容不透视；Risograph：纸色底 + 墨线上下边框，保持原配色 |
| 层级 | `z-index: 1030`（低于首屏 loader 的 9999，高于内容与侧栏） |
| 移动端 | 同规则生效（吸顶不区分断点）；不改变导航内部布局 |
| 不改动 | 侧栏 sticky、图表、卡片、页面结构与交互均不动 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `themes/corporate-clean/static/.../corporate-clean.css` | `.r-nav` 吸顶 |
| `themes/risograph/static/.../risograph.css` | `.r-nav` 吸顶 |
| `plugin_host/tests.py` | 两套主题 `.r-nav` sticky / z-index 断言 |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移、无 Python / 模板结构变化。

## 四、验收口径

1. 两套主题滚动长页面时顶部导航保持置顶，内容从其下方经过；
2. 导航不遮挡首屏内容（sticky 占位，不脱离文档流）；
3. 侧栏 sticky 行为不受影响；移动端导航同样吸顶；
4. 既有测试不回归，Docker 重建后静态 CSS 生效。

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| 实现 | 两套主题 `.r-nav` 已加 `position: sticky; top: 0; z-index: 1030` |
| Docker 部署 | `docker compose up -d --build` 成功；`constellatio-web-1` 运行，静态 CSS 含新规则（两主题各 1 处 `z-index: 1030`） |
| 自动化测试 | 按要求**未执行**，交由负责人在页面上验证滚动吸顶效果 |

