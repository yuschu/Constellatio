# 插件开发文档：v1.5.17 重新申请表单化 + 审批终态

> 关联插件：approval（重新申请 / 详情 / 抄送）、notify 计划（站内信）
> 版本：v1.5.17 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（184 项测试全绿 + 迁移 0007 + Docker 重建 + 冒烟）

## 一、需求

1. **重新申请**：点「重新申请」进入**申请界面可修改内容**，确认后重新发起，并**替换被驳回记录**；
2. **审批操作二次确认后不可修改**；
3. **审批详情隐藏空内容项**；
4. **抄送我的对 L3 用户隐藏**；
5. 添加**站内信插件开发计划**。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 重新申请入口 | 列表「重新申请」→ `GET /plugins/approval/new/?reapply=<id>`（仅申请人 + 已驳回，否则 302） |
| 表单 | 预填原单 `form_data` + 部门 / 审批人；类型固定（不显示类型 Tab）；提交带隐藏 `reapply_of` |
| 替换语义 | 提交成功：新单 pending；原单 `replaced_by=新单` 且 `applicant_hidden=True`，写 `replaced` 流转记录（备注新单号）；「我发起的」不再显示原单，数据与留痕保留 |
| 附件 | 用章重申请需**重新上传文件**（浏览器无法预填 file input），原附件仍在原单可查 |
| 二次确认 | 通过 / 驳回 / 会签按钮加 `data-confirm`，页面脚本 `window.confirm` 拦截；无内联 onclick |
| 终态不可修改 | `_can_act` 增加「仅 pending」判定；已处理详情不再渲染操作区，显示「该申请已处理，不可修改。」；服务层状态机兜底 |
| 空内容项 | 表单动态字段值为空 → 不渲染该行；部门 / 金额 / 抄送区无值时不渲染（不再显示 `—`） |
| 抄送我的 | 菜单 perm 与视图均改为 `approval_approve`（L3 隐藏；审批中心仍对 L3 开放） |
| 数据 | 新增 `Approval.replaced_by` 自关联 + 迁移 `approval/0007` |
| 站内信计划 | 见 `docs/plugin-dev-notify.md`：`plugins/notify` + `Notification` 模型 + 消息中心 / 未读数，v1.15 |

## 三、测试

- 重新申请：GET 表单 200 且预填；POST 修改后生成新单、原单 replaced_by / 隐藏 / `replaced` 记录；列表不再显示原单；
- 守卫：非驳回 / 非申请人不能进入重申请（302 / 404）；
- 详情：空事由 / 无金额 / 无抄送不渲染；终态无操作区并显示「已处理」；
- 抄送我的：L3 302、管理岗 200；
- 既有 180 项不回归。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/approval/models.py` + `migrations/0007_approval_replaced_by.py` | `replaced_by` |
| `plugins/approval/views.py` | create 支持 reapply_of / 替换原单；删除一键 reapply 视图；`_can_act` 终态；详情过滤空行；CC 权限 |
| `plugins/approval/urls.py` | 移除 reapply 路由 |
| `plugins/approval/apps.py` | 抄送我的 perm |
| `approval_list.html` / `approval_form.html` / `approval_detail.html` | 入口、预填表单、二次确认、空项隐藏、终态提示 |
| `plugins/approval/tests_v155.py` | 重写 / 新增 7 项 |
| `docs/plugin-dev-notify.md` | 补站内信章节 |
| `locale/.../django.po` / `roadmap.md` / `README.md` | 同步 |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 新增 `approval/0007_approval_replaced_by`；`makemigrations --check` 干净 |
| 全量单测 | **184 项通过**（基线 180，重写 1 + 新增 5） |
| Docker 重建 | `docker compose up -d --build` 成功，entrypoint 已执行迁移 |
| 重申请冒烟 | 列表出现 `/new/?reapply=<id>`；表单 200 且预填原内容与「确认重新发起」；提交修改后生成新单，原单从列表隐藏 |
| 替换留痕 | 原单详情显示「已替换」及 `被 #新单 替换` |
| 空项隐藏 | 只填时间的请假详情不渲染「事由」「金额」行 |
| 终态 | 待审批详情含二次确认文案；通过后无操作区，显示「该申请已处理，不可修改」 |
| 抄送 | `hr_qian`（L3）访问 302；HR 经理 200 |
| 数据清理 | 冒烟产生的审批单已删除 |
