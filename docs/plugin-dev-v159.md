# 插件开发文档：v1.5.9 合并组织架构与模板详情

> 关联插件：structure（页面与数据）、user（`Department` / `Role` / `User`）
> 版本：v1.5.9 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（163 项测试全绿 + Docker 重建 + 双视角冒烟）

## 一、需求

1. **合并「组织架构」与「应用结构」模块**：侧栏只保留一个「组织架构」入口，不再单列「应用结构」。
2. **组织架构页展示当前架构**：真实部门树、真实角色、用户关系树（责任划分）与责任人清单。
3. **模板架构独立查看**：点击【查看模板】进入模板详情（弹窗或页面），看模板部门 / 角色 / 用户；应用模板动作留在模板页。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 菜单 | structure 只保留一个菜单：`组织架构`（`structure_view`，`/plugins/structure/`）；删除「应用结构」菜单 |
| 总览页 | **当前架构**：统计（部门 / 角色 / 账号 / 汇报链起点）、真实部门树（含成员数、停用标记）、真实角色（权限数 + 成员数）、用户关系树 + 责任人清单、最近应用记录 |
| 模板详情 | 独立页面 `/plugins/structure/template/`（不弹窗：20 部门 + 31 角色 + 31 用户模板内容较多，页面更清晰且可直达/可刷新）。要求 `structure_view` |
| 查看模板入口 | 总览页标题右侧【查看模板】按钮 → 模板详情页；模板页有「← 返回组织架构」 |
| 应用模板 | 表单只在模板页（`structure_manage`）；勾选 `grant_manager_perms` 可选；成功后回模板页并写入应用记录 + 上链 |
| 数据来源 | 当前架构读真实 `user.Department` / `user.Role` / `user.User`；模板架构读 `structure/template.py` 常量 |
| 存储 | 不新增表、无迁移 |
| 权限 | 总览 = `structure_view`；模板详情 = `structure_view`；应用 = `structure_manage`（按钮与表单只对有权限者渲染，视图仍 `require_perm` 兜底） |
| 空态 | 真实部门 / 角色为空时显示引导文案（先去用户管理创建，或到模板页应用模板） |

## 三、实现

### 3.1 数据

`plugins/structure/hierarchy.py` 新增 `build_department_tree()`：
- 返回 `{'roots': [...], 'stats': {'total', 'active', 'members'}}`；
- 节点：`name / is_active / member_count / children`；
- 根 = `parent` 为空（或上级缺失）的部门；成员数按 `User.department_id` 聚合。

### 3.2 视图 / 路由

| 路由 | 视图 | 权限 | 说明 |
|---|---|---|---|
| `/plugins/structure/` | `structure_overview` | `structure_view` | 当前架构（真实数据）+ 最近应用 |
| `/plugins/structure/template/` | `structure_template`（新增） | `structure_view` | 模板部门 / 角色 / 用户 + 应用表单（`structure_manage`） |
| `/plugins/structure/apply/` | `structure_apply`（POST） | `structure_manage` | 应用模板后回模板页 |

### 3.3 页面

- `structure/overview.html`：重写为当前架构；标题右侧【查看模板】。
- `structure/template.html`：新增；模板架构 + 返回链接 + 应用表单。

## 四、测试计划

1. 菜单：structure 只注册 1 个菜单（组织架构），不再有应用结构；
2. 总览：显示真实部门名 / 真实角色名 / 成员数；`structure_view` 守卫不变；
3. 模板页：`structure_view` 200，含模板部门 / 角色 / 用户与【查看模板】来源；`structure_manage` 才渲染应用表单；
4. 应用：POST 成功回模板页、写记录、信号不变；无权限 302；
5. 部门树：真实层级 / 成员数 / 停用标记；
6. 回归：关系树、权限守卫、既有 158 项测试。

## 五、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/structure/hierarchy.py` | `build_department_tree()` |
| `plugins/structure/views.py` / `urls.py` / `apps.py` | 总览改真实数据、模板页、菜单合并 |
| `templates/structure/overview.html` | 重写当前架构 |
| `templates/structure/template.html` | 新增模板详情 + 应用表单 |
| `plugins/structure/tests.py` | 新增 / 调整单测 |
| `locale/en/LC_MESSAGES/django.po` | 新文案 |
| `docs/plugin-dev-structure.md` / `roadmap.md` / `README.md` / 快照 | 同步 |

## 六、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **163 项通过**（基线 158 + 新增 5） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 组织架构页 | 200：当前部门树（研发部等真实部门）、当前角色（人力资源经理等）、关系树、责任人清单、【查看模板】入口；不再出现模板区块 |
| 模板详情页 | 200：模板部门树 / 模板角色 / 用户模板 / 返回组织架构 / ⤓ 应用模板（管理员可见） |
| 权限 | `hr_qian`（L3）访问总览与模板页均 302；员工侧栏无组织架构入口 |
| 菜单 | 侧栏只剩「组织架构」，不再出现「应用结构」 |
