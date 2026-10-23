# 插件开发文档：v1.5.10 角色卡片弹窗与滚动

> 关联插件：structure（组织架构页）、user（`Role` / `User` / `Department`）
> 版本：v1.5.10 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（164 项测试全绿 + Docker 重建 + 冒烟）

## 一、需求

组织架构页「当前角色」卡片：

1. **支持点击**：弹出弹窗（Bootstrap modal）展示该角色下的具体人员（姓名 / 账号 / 部门 / 停用标记）；
2. **增加滚动条、自适应大小**：角色列表容器限高并可滚动，高度随视口自适应。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 数据 | `structure_overview` 的 `role_rows` 增加 `members`（姓名 / 账号 / 部门 / 是否停用）；`prefetch_related('users__department')` 避免 N+1 |
| 展示 | 角色从表格改为**角色卡片列表**：名称 + 权限数徽标 + 成员数徽标；整卡可点击 |
| 弹窗 | 单个可复用 Bootstrap 5 modal（避免 31 个 modal）；标题=角色名，正文=成员列表，空角色显示「该角色暂无成员」 |
| 数据传递 | `role_rows|json_script:"role-members"` 注入；前端按 `data-role-index` 取对应角色，`textContent` 渲染（不拼 HTML，避免 XSS） |
| 滚动 | 容器 `overflow-y:auto`，`max-height:min(60vh, 32rem)`，`flex-grow-1 + min-height:0`；随视口/卡片高度自适应 |
| 交互约束 | 不新增内联 `onclick`；事件监听在页面脚本中绑定；无 JS 时卡片不可点但不影响页面其他功能 |
| 权限/数据 | 仍 `structure_view`；不新增表、无迁移、无新路由 |
| 双语 | 新增文案补 `.po`：角色成员 / 点击角色查看成员 / 共 {count} 人 / 该角色暂无成员 / 关闭 |

## 三、实现

- `plugins/structure/views.py`：`role_rows` 从 annotate 改为 prefetch 后组装 `members`，`perm_count/member_count` 由成员/权限列表长度得出。
- `templates/structure/overview.html`：当前角色卡片 → 滚动容器 + 角色卡片按钮 + 复用 modal + `json_script` + 页面脚本。
- 主题：只用 Bootstrap 工具类与既有 `r-badge`，不改主题 CSS。

## 四、测试计划

1. 视图上下文：角色 `members` 含账号 / 姓名 / 部门；`member_count` 与成员数一致；
2. 页面：含 `role-scroll`、`data-role-index`、`roleModal`、`role-members` 与成员 JSON；
3. 空角色：JSON 中 `members: []`、`member_count: 0`（弹窗显示空态文案）；
4. 回归：既有 163 项不回归；双语页面。

## 五、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/structure/views.py` | role_rows 携带 members（prefetch） |
| `templates/structure/overview.html` | 角色卡片 + 滚动 + 弹窗 + 脚本 |
| `plugins/structure/tests.py` | 新增 1 项（成员数据 / 弹窗标记 / 滚动容器） |
| `locale/en/LC_MESSAGES/django.po` | 新增文案 |
| `docs/plugin-dev-structure.md` / `roadmap.md` / `README.md` / 快照 | 同步 |

## 六、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **164 项通过**（基线 163 + 新增 1） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 页面冒烟 | 组织架构页 200：`role-scroll` + `overflow-y:auto`、`data-role-index`、`roleModal`、`role-members`、空态与计数文案齐全 |
| 数据冒烟 | `role-members` JSON 含 `hr_qian`（招聘专员）及部门；`hr_wang` 视角同样渲染弹窗骨架 |
