# 插件开发文档：v1.5.15 审批路由与用章盖章占位

> 关联插件：approval（路由 / 调休 / 盖章占位）、user（部门 / 角色）、plugin_host（工作台入口）
> 版本：v1.5.15 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（177 项测试全绿 + Docker 重建 + 冒烟）

## 一、需求

1. **L3 用户隐藏「待我审批」**（侧栏、工作台卡片、页面入口）；
2. **调休时间改为时间段**（开始 / 结束，结束须晚于开始）；
3. **用章审批通过后电子盖章**：调用电子章插件（待开发），当前用文本占位；
4. **不同审批类型流转到对应管辖部门管理用户**；
5. 新增**信息提醒插件**开发计划（站内信 / 公告 / 审批信息）。

## 二、设计口径（契约）

### 2.1 L3 隐藏待我审批

- 侧栏「待我审批」菜单 `perm` 改为 `approval_approve`（L2+ / 超管可见）；
- 视图 `approval_pending` 改 `@require_perm('approval_approve')`（L3 直接 302）；
- 工作台「待我审批」卡片与计数仅 `approval_approve` 可见（`can_approve` 上下文）；
- 审批中心 / 抄送我的仍为 `approval_view`（L3 可用）。

### 2.2 调休时间段

- `CompForm`：`start_time*`（调休开始时间）、`end_time*`（调休结束时间），沿用 `BaseApprovalForm.clean` 校验结束晚于开始；
- 展示字段：`start_time / end_time / basis`；调休依据仍必填（关联加班记录）。

### 2.3 电子盖章（占位）

- `plugins/approval/eseal.py`：`apply_e_seal(approval)` 写入 `form_data['e_seal'] = {'status': 'placeholder', 'text': ...}` 并返回文本；
- `services.approve`：审批类型为用章时，在通过记录后调用占位盖章并写 `e_seal` 流转记录（不改变状态）；
- 详情页展示「电子盖章 · 待接入」+ 占位说明；流转记录动作显示「电子盖章」；
- 真实电子章插件接入时只替换 `eseal.apply_e_seal` 实现，不改审批流程。

### 2.4 审批类型 → 管辖部门路由

`plugins/approval/routing.py`：

| 审批类型 | 管辖部门 | 目标管理用户 |
|---|---|---|
| 请假 / 外出 / 加班 / 调休 | 人力资源部 | 人力资源经理角色 → 部门内 `approval_approve` 用户 |
| 报销 | 财务部 | 财务经理角色 → 部门内 `approval_approve` 用户 |
| 用章 | 行政部 | 行政经理角色 → 部门内 `approval_approve` 用户 |

- 解析顺序：路由命中 → 表单手动审批人 → 直属上级 → 超管；
- 路由优先于手动选择；部门或经理缺失时回退，不阻断发起；
- 抄送规则不变（审批人上级）。

## 三、测试

- L3 访问待我审批 302、首页无入口；管理岗 200 且有入口；
- 调休时间段校验（结束早于开始被拦）与提交；
- 报销路由到财务经理（优先于手动指定的总经理）；请假路由到 HR 经理；无对应部门时回退直属上级；
- 用章通过后 `form_data.e_seal` 占位写入、`e_seal` 流转记录存在、详情显示「电子盖章 / 待接入」；
- 既有 172 项不回归。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/approval/forms.py` | 调休起止时间、审批人帮助文案 |
| `plugins/approval/routing.py`（新增） | 类型 → 管辖部门路由 |
| `plugins/approval/eseal.py`（新增） | 电子章占位接口 |
| `plugins/approval/services.py` | 用章通过后触发占位盖章 |
| `plugins/approval/views.py` | 待办权限、路由审批人 |
| `plugins/approval/apps.py` | 待办菜单权限 |
| `approval/approval_detail.html` / `approval_form.html` | 电子章展示、路由说明 |
| `plugin_host/views.py` + `themes/*/home.html` | 工作台待办卡片按 approval_approve 收敛 |
| `plugins/approval/tests_v155.py` | 新增 5 项 |
| `docs/plugin-dev-notify.md`（新增） | 信息提醒插件开发计划 |
| `locale/en/LC_MESSAGES/django.po` / `roadmap.md` / `README.md` | 同步 |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 无新迁移（`makemigrations --check` 干净） |
| 全量单测 | **177 项通过**（基线 172 + 新增 5） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 运行 |
| L3 冒烟 | `hr_qian` 首页无待我审批入口，直接访问 `/plugins/approval/pending/` 302 |
| 调休冒烟 | 表单渲染「调休开始时间 / 调休结束时间」；结束早于开始被单测拦截 |
| 路由冒烟 | 报销单审批人=郑经理（财务经理）；用章单审批人=黄经理（行政经理） |
| 盖章冒烟 | 行政经理通过用章后，详情显示「电子盖章 · 待接入」与占位文本，流转记录含电子盖章 |
| 数据清理 | 冒烟产生的报销 / 用章审批单已删除 |
