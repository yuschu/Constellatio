# 插件开发文档：v1.5.11 组织架构角色列表布局修正

> 关联插件：structure（组织架构页）
> 版本：v1.5.11 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（164 项测试全绿 + Docker 重建 + 布局标记冒烟）

## 一、问题

组织架构页「当前角色」列表右侧/底部出现**无效空白**，与左侧「当前部门树」留白不协调：

- 内层 `.role-scroll` 用 `max-height:min(60vh, 32rem)` 限高；
- 外层 `.r-card h-100` 被左侧部门树撑高（Bootstrap row 默认 stretch）；
- 卡片高度 > 滚动区高度，剩余空间变成空白带；左右卡片高度/填充不一致。

## 二、修正方案

| 项 | 决策 |
|---|---|
| 等高 | `row align-items-stretch` + 两列 `col-md-6 d-flex` + 卡片 `h-100 w-100`，左右卡片严格等高同宽 |
| 限高 | 高度上限收敛到**卡片本身**（`max-height:min(62vh, 34rem)` + `overflow:hidden`），不再在内层列表上单独限高 |
| 填充 | 卡片 `d-flex flex-column`；列表容器 `flex-grow-1; min-height:0; overflow-y:auto`，内容区自适应撑满卡片 |
| 部门树 | 同步改为内部滚动（同一高度口径），避免左卡溢出或被裁切 |
| 滚动 | 角色条目多 → 仅右卡内部滚动；条目少 → 列表容器仍撑满卡片，不再出现空白带 |
| 后端 | 无变化：视图、数据、权限、路由、迁移均不动 |

## 三、验收

- 左右卡片等高；「当前角色」卡片宽度撑满列，无侧向空白；
- 31 个角色时右卡内部出现滚动条，页面不被拉长；
- 部门树较高时同样内部滚动，两卡视觉高度一致；
- 移动端（<768px）两卡上下堆叠，各自限高滚动。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/structure/templates/structure/overview.html` | 左右卡片等高 + 内层滚动布局 |
| `plugins/structure/tests.py` | 断言新布局标记 |
| `docs/roadmap.md` / `README.md` / 快照 | 同步（快照按需生成） |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **164 项通过**（断言新增到既有角色卡片测试） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 布局冒烟 | `align-items-stretch` 1 处、`max-height:min(62vh, 34rem)` 2 处（左右卡片各一）、旧内层限高 `60vh/32rem` 已移除、角色列表与部门树均为 `flex-grow-1 + overflow-y:auto + min-height:0`、弹窗元素保留 |
| 视觉结果 | 左右卡片等高同宽；角色多时仅右卡内部滚动，页面不被拉长；无底部空白带 |
