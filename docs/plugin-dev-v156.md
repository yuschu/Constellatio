# 插件开发文档：v1.5.6 用户关系树（责任划分）

> 关联插件：structure（页面与树构建）、user（`User.leader` 数据源）
> 版本：v1.5.6 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（144 项测试全绿 + 本地 HTTP 三视角冒烟；Docker 重建待验证）

## 一、需求

「组织架构」页要显示**用户关系树**，把每个账号对应的**直属上级**梳理出来，用于责任划分：

- 一眼看清谁向谁汇报（多级汇报链，不止上下两级）；
- 每个责任人能看到自己的**直接下属**与**含下级合计**规模；
- 无上级、成环、停用等异常能显式暴露，而不是静默丢节点。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 数据源 | 真实 `user.User` 记录（含超管），**不用** `structure/template.py` 的静态 `USERS` 模板；上级口径唯一来源 `User.leader` |
| 树关系 | 账号挂在其 `leader` 节点下；`leader` 为空的账号是**根节点**（汇报链起点） |
| 成环 | A→B、B→A 这类环：环上节点**提为根节点**并标「汇报环」，环内边断开，页面不递归死循环、节点不重复 |
| 停用账号 | 保留在树中并标「停用」；上级停用**不拆树**（历史责任链仍可见） |
| 上级被删除 | `leader` 为 `SET_NULL`，该账号自然成为根节点，无需额外补偿 |
| 统计口径 | 直接下属 = `leader` 指向本人的账号数；含下级合计 = 子树账号数（不含本人） |
| 存储 | **不新增业务表、无迁移**，纯只读计算 |
| 权限 | 沿用总览 `structure_view`；不做行级数据权限（与 v1.5.5「签到详情为页面级权限」口径一致） |
| 边界 | 不提供拖拽/就地改上级；上级调整仍走用户管理 `leader` 字段 |

## 三、实现

### 3.1 新增模块

`plugins/structure/hierarchy.py`

- `build_user_tree()` → `{'roots': [node...], 'rows': [row...], 'stats': {...}}`
- `node`：`id / name / account / dept / roles / level_label / is_active / is_cycle / depth / direct_count / total_count / leader_name / children`
- `stats`：`total / with_leader / roots / cycles / inactive`
- 环检测：沿 `leader` 向上走到重访节点即判定环，环上账号的向上边断开；再自根 DFS 构建子树（带 visited 保护）
- `rows`：按树的先序展开（根 → 子树），用于「责任人清单」表，保证与树同序

### 3.2 视图

`plugins/structure/views.py::structure_overview` 注入：

- `org_roots`（树）、`org_rows`（清单）、`org_stats`（统计）
- 顺带修复 v1.5.x 遗留缺陷：`users_by_dept` 已计算但**未注入上下文**，导致「用户模板」分组区块空白

### 3.3 页面

`/plugins/structure/`（`structure/overview.html` + 递归片段 `structure/_tree_node.html`）：

1. 新增「用户关系树（责任划分）」卡片：4 个统计（账号总数 / 已设直属上级 / 汇报链起点 / 汇报环 + 停用）+ 多级树；节点显示姓名、账号、部门、角色徽标、直接下属数、停用/环标记。
2. 新增「责任人清单」表：姓名 / 账号 / 部门 / 角色 / 直属上级 / 直接下属 / 含下级合计 / 状态，按树先序排列。
3. 既有部门树、角色清单、用户模板分组保持不动（用户模板分组改为真实渲染）。

## 四、路由与权限

| 路由 | 视图 | 权限 | 变化 |
|---|---|---|---|
| `/plugins/structure/` | `structure_overview` | `structure_view` | 页面增区块（无新路由、无新菜单） |

## 五、测试计划

单测（`plugins/structure/tests.py`）：

1. 根/子/孙层级与 `depth`、直接下属数、含下级合计正确；
2. 多个无上级账号 → 多个根；
3. A→B→A 成环：两节点都进根列表、标 `is_cycle`、不递归、行不重复；
4. 停用账号保留且标停用，统计 `inactive` 正确；
5. 总览页 `structure_view` 200 且含关系树/清单；无权限 302；
6. 回归：应用模板后「用户模板」分组真实渲染（`users_by_dept` 注入）。

冒烟：Docker 重建 → admin / hr_wang / hr_qian 三视角打开 `/plugins/structure/`；中英切换。

## 六、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/structure/hierarchy.py` | 新增：树构建 + 环检测 + 统计 + 清单 |
| `plugins/structure/views.py` | 注入树/清单/统计，修复 `users_by_dept` |
| `plugins/structure/templates/structure/overview.html` | 增关系树卡片与责任人清单 |
| `plugins/structure/templates/structure/_tree_node.html` | 新增：递归节点片段 |
| `plugins/structure/tests.py` | 新增 6 组单测 |
| `locale/en/LC_MESSAGES/django.po` | 新增本轮文案 |
| `docs/roadmap.md` / `docs/plugin-dev-structure.md` / `session/*-v1.5.6-Session.md` | 路线、插件文档、快照同步 |

## 七、不做（明确移出范围）

- 不做组织架构图可视化（关系树为结构化列表树；图形化留待图表插件化版本）
- 不做部门维度权限隔离、不做上级变更审批流
- 不改 `User.leader` 字段语义与审批「留空自动指派直属上级」逻辑

## 八、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **144 项通过**（基线 138 + 新增 6） |
| HTTP 冒烟（本地 sqlite 独立冒烟库，template 31 账号 + admin） | admin / hr_wang：结构页 200，关系树与责任人清单渲染，张总直接下属 11；hr_qian：302 收敛回工作台；英文切换 `Reporting tree (responsibility)` / `11 direct report(s)` 正常 |
| Docker 重建 | **未执行**（本机 Docker Desktop 引擎管道在当前会话不可达），待负责人环境验证 |

> 冒烟用独立 `smoke.sqlite3`（已删除，未入库）；`db.sqlite3` 仍是旧快照结构（缺 `leader` 列），不用于冒烟。
