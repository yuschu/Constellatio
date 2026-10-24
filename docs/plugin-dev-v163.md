# 插件开发文档：v1.6.3 工作台 Banner 白字 + 侧栏吸顶

> 关联：themes（Corporate Clean / Risograph 模板与主题 CSS）
> 版本：v1.6.3 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（234 项测试全绿 + Docker 重建；待收尾 tag / push）

## 一、需求

1. **Corporate Clean 主题**：工作台顶部蓝色 Banner 的「工作台」标题与「欢迎 admin」文字改为**白色字体**；
2. **Risograph 主题保持原有配色**，两个主题互不影响；
3. **左侧功能侧边菜单固定悬浮**：页面纵向滚动时菜单不跟随滚动（桌面端吸顶，菜单过高时栏内滚动）；
4. 其余图表、卡片、布局、交互逻辑**全部不变**。

## 二、设计口径

| 项 | 决策 |
|---|---|
| Banner 白字 | 仅 Corporate Clean CSS：`.r-hero` / `.r-hero h2` 改 `#ffffff`，`.r-hero-text` 改 `rgba(255,255,255,.92)`；Risograph 的 hero 是纸色卡片，CSS 不动 |
| 侧栏吸顶 | 两套主题统一：`@media (min-width: 768px) { .r-card--sidebar { position: sticky; top: 1rem; max-height: calc(100vh - 2rem); overflow-y: auto; } }` |
| 覆盖范围 | 侧栏规则对所有带 `r-card--sidebar` 的页面生效（外壳统一），移动端（<768px）保持随页滚动 |
| 主题互不影响 | 白字只写在 `corporate-clean.css`；Risograph 基础模板仅补 `r-card--sidebar` 钩子类，不改配色 |
| 布局 | 不改任何模板结构 / 卡片 / 图表 / 交互 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `themes/corporate-clean/static/.../corporate-clean.css` | hero 白字 + 侧栏吸顶 |
| `themes/risograph/static/.../risograph.css` | 侧栏吸顶 |
| `themes/risograph/templates/base.html` | 侧栏卡片补 `r-card--sidebar` 钩子类 |
| `plugin_host/tests.py` | 新增主题契约断言（白字仅 Corporate、两主题吸顶） |
| 文档 | 本文件 + roadmap / README |

无新表、无迁移、无 Python 逻辑变化。

## 四、验收口径

1. Corporate Clean 工作台 Banner 标题与欢迎语为白字；Risograph 不出现该白字规则；
2. 桌面端滚动长页面（如管理员工作台）时，左侧菜单保持吸顶，不随内容滚走；菜单超长时栏内滚动；
3. 移动端布局不变，菜单随页滚动；
4. 既有测试不回归，Docker 重建后两套主题静态资源生效。

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| 全量单测 | **234 项通过**（v1.6.2 基线 231 + 新增 3：Corporate 白字 / Risograph 不变 / 两主题吸顶） |
| Corporate 白字 | `.r-hero h2` → `#ffffff`，`.r-hero-text` → `rgba(255,255,255,.92)`；Docker 内静态资源核验通过 |
| Risograph 不变 | 主题 CSS 无 `.r-hero` 规则（首页为纸色卡片 + 字模标记），配色未改动 |
| 侧栏吸顶 | 两套主题均含 `position: sticky; top: 1rem; max-height: calc(100vh - 2rem); overflow-y: auto;`（≥768px）；Risograph 侧栏补 `r-card--sidebar` 钩子类 |
| 移动端 | <768px 不吸顶，保持随页滚动；布局与图表未改 |
| Docker 重建 | `docker compose up -d --build` 成功；`constellatio-web-1` 启动，静态 CSS 已更新（collectstatic） |

