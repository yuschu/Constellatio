# 插件开发文档：RBAC 权限等级与插件准入（v1.5.4）

> 关联插件：user（权限等级 / 角色模板权限）、attendance（签到详情）、structure（角色权限模板）、approval / blockchain / workspace（视图准入）
> 版本规划：v1.5.4 · 文档版本：v1.0 · 2026-10-22
> 状态：**✅ 已实现**（102 项测试全绿；Docker 部署供负责人验收）

## 一、需求

1. **对应角色需拥有对应权限**：角色不再是"空壳身份"，应用组织架构模板时按角色职责授予对应权限码。
2. **优化权限等级**：权限码按 L0–L3 分级，角色/权限页面显示等级，授予范围受操作者自身权限约束。
3. **设置好对应模板的权限**：`structure` 模板内置 `ROLE_PERMISSIONS`，应用模板即幂等授予（只增不减）。
4. **拥有相应权限则可使用对应的插件**：插件内每个受控视图统一走 `require_perm` 守卫，菜单与 URL 口径一致，无权限重定向工作台。
5. **考勤、公告等所有用户都能使用**：`attendance_view` / `attendance_check` / `notice_view` 作为**全员基线权限**，任何已登录且未冻结的账号天然拥有，无需分配角色。
6. **管理岗可查看签到详情（拥有对应权限）**：新增 `attendance_report_view`（L2 管理岗），提供 `/plugins/attendance/records/` 签到详情页（按月份 / 部门 / 姓名筛选 + 汇总 + 分页）。

## 二、权限等级（`plugins/user/perms.py`）

数字越小权限越高；同一权限只属于一个等级。

| 等级 | 名称 | 判定 | 典型权限码 |
|---|---|---|---|
| L0 | 超级管理员 | `is_superuser=True`（直接放行） | 全部 |
| L1 | 系统管理 | 角色/直接权限含 L1 码 | `user_manage` / `workspace_manage` / `structure_manage` / `blockchain_verify` |
| L2 | 管理岗 | 角色/直接权限含 L2 码 | `dept_delete_approve` / `user_disable_approve` / `approval_approve` / `attendance_report_view` / `notice_manage` / `structure_view` / `blockchain_view` |
| L3 | 员工 | 仅 L3 码或仅基线 | `approval_view`（基线权限码见下） |

- **全员基线权限**：`attendance_view`（考勤看板）、`attendance_check`（打卡）、`notice_view`（公告浏览）。
  - 判定顺序：`permission_frozen` → 拒绝；`is_superuser` → 通过；未激活 → 拒绝；基线码 → 通过；直接权限 → 角色权限。
  - 基线权限不需要、也不能通过角色分配来获得；因此"所有用户都能用考勤/公告"不依赖模板或角色。
- `permission_frozen=True` 时**基线权限同样失效**（冻结语义 = 登录但无操作权限）。
- 角色等级 = 角色权限中的最高等级（空权限按 L3）；用户等级 = 超管 L0 / 自身权限最高等级 / 默认 L3。
- 授予约束沿用 v1.5.3：`grantable_permissions` / `grantable_roles` 只展示操作者自身拥有的权限，禁止越级授权。

## 三、角色 → 权限模板（`plugins/structure/template.py`）

| 角色组 | 角色 | 模板权限（除基线外） |
|---|---|---|
| 总经理 | 总经理 | L2 管理岗全套 + `user_manage` |
| 部门经理 | 人力资源 / 财务 / 市场 / 销售 / 研发 / 运营 / 客服 / 行政 / 法务 / 采购 / IT 经理 | `approval_view` `approval_approve` `attendance_report_view` `notice_manage` `blockchain_view` `structure_view` |
| HRBP | HRBP | `approval_view` `attendance_report_view` `structure_view` |
| 系统管理 | 系统管理员 | L1 全套 + L2 只读/审批 + `blockchain_verify` |
| 其他员工 | 专员 / 工程师 / 会计 / 出纳 / 产品经理 / UI 设计师等 | `approval_view` |

- `apply_structure()` 对 `ROLE_PERMISSIONS` **幂等补齐**（`role.permissions.add`，只增不减，不覆盖人工调整）；
- 老库升级：执行 `python manage.py grant_role_perms`（可加 `--dry-run` 预览）为既有角色补齐模板权限；加 `--revoke-manager-perms` 可收回部门经理的 L1 `user_manage`（保留总经理/系统管理员），让管理岗回到 L2；
- 原 `grant_manager_perms` 开关保留：**默认关**，勾选时额外给经理类角色 `user_manage`（L1）；模板权限本身不依赖该开关。全局仅 `总经理` 与 `系统管理员` 默认持 L1，部门经理保持 L2，避免越级；
- 角色权限码不存在（插件停用/迁移未跑）时跳过该码，不抛异常。

## 四、插件准入矩阵

| 插件 | 视图 | 准入 | 菜单 |
|---|---|---|---|
| auth | 登录 / 登出 / 忘记密码 | 公开 | — |
| notice | 列表 / 详情 | 登录即可（全员） | 公告中心（全员） |
| notice | 发布 | `notice_manage`（L2） | 列表内按钮 |
| attendance | 看板 / 打卡 | 登录即可（全员基线） | 考勤打卡（全员） |
| attendance | **签到详情** | `attendance_report_view`（L2） | 签到详情（管理岗） |
| approval | 我发起的 / 待我审批 / 发起 | `approval_view`（L3，模板全员授予） | 审批中心 / 待我审批 |
| approval | 详情 | 申请人 / 审批人 / `approval_view` | — |
| blockchain | 列表 / 详情 | `blockchain_view`（L2） | 留痕链（管理岗） |
| structure | 总览 | `structure_view`（L2） | 组织架构（管理岗） |
| structure | 应用模板 | `structure_manage`（L1） | 应用结构（L1） |
| user | 部门 / 用户 / 角色 / 个人中心 | `user_manage`（L1）；个人中心仅本人 | 部门 / 用户 / 角色 |
| workspace | 插件开关 | `workspace_manage`（L1） | 插件开关（L1） |

- 统一守卫：`plugin_host/permissions.py::require_perm(codename)` —— 未登录 → 登录页；无权限 → 工作台（302）。
- 菜单过滤走 `get_menus(user)` → `user.has_perm(perm)`，与 URL 守卫同源，保证"看得到 = 进得去"。
- 插件被 workspace 停用时，路由中间件仍先行 404（与权限无关）。

## 五、签到详情页

- 路由：`/plugins/attendance/records/`，`name=attendance_records`。
- 权限：`attendance_report_view`（L2 管理岗），迁移 `attendance.0002` 创建权限码。
- 筛选：月份（默认当月，非法回退当月）、部门（跨插件 `apps.get_model('user','Department')`，零 import）、姓名/账号关键字。
- 展示：日期 / 姓名 / 账号 / 部门 / 签到 / 签退 / 状态（正常 / 迟到 / 缺卡）；汇总卡片（记录数、涉及人数、迟到次数）；每页 25 条。
- 迟到口径与看板一致：签到时间晚于 09:00。

## 六、验收

- [ ] `attendance_report_view` 权限码随迁移创建，模板应用后管理岗角色拥有、专员没有。
- [ ] 无角色账号可打开考勤看板、打卡、查看公告；不能打开签到详情 / 留痕链 / 组织架构 / 插件开关。
- [ ] 管理岗角色（如人力资源经理）可打开签到详情并看到他人记录；普通专员 302 回工作台。
- [ ] 菜单可见性与 URL 守卫一致。
- [ ] `python manage.py check` 0 issue；全量单测通过（76 基线 + 新增）。
- [ ] Docker 重建后中英文页面、签到详情、权限等级显示、留痕/组织架构准入冒烟通过。

## 七、边界

- 不做"数据级行权限"（如部门经理只看本部门签到）；本版为插件/页面级准入，行级范围留作后续版本。
- 不做权限审批流（授予 L1 权限仍需人工复核）；越级授权仅靠"只能授予自身已有权限"约束。
- 基线权限不写库、不显示在"直接权限"列表；在"我的权限"页单独标注。
