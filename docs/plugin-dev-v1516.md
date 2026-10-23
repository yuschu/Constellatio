# 插件开发文档：v1.5.16 已驳回申请的重新申请与隐藏

> 关联插件：approval（我发起的列表 / 详情 / 流转记录）
> 版本：v1.5.16 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（180 项测试全绿 + 迁移 0006 + Docker 重建 + 冒烟）

## 一、需求

已驳回的申请可：

1. **重新申请**：复制原单内容重新发起（进入待审批）；
2. **删除申请记录**：实际是**对申请人隐藏**，数据与审批留痕保留。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 新增字段 | `Approval.applicant_hidden`（bool，默认 False），迁移 `approval/0006` |
| 重新申请 | `POST /plugins/approval/<id>/reapply/`：仅**申请人 + 已驳回**；复制类型 / 标题 / 内容 / 部门 / 金额 / 附件 / `form_data`；清除旧 `e_seal`；审批人按当前路由重算，缺失回退原审批人；新单进入 pending 并写 `resubmit` 流转记录（备注原单号） |
| 删除（隐藏） | `POST /plugins/approval/<id>/hide/`：仅**申请人 + 已驳回**；置 `applicant_hidden=True`；不删除记录、不改状态 |
| 列表 | 「我发起的」过滤 `applicant_hidden=False`；审批人 / 抄送人视图不受影响 |
| 详情 | 隐藏后申请人仍可通过历史链接访问（数据保留）；审批链留痕完整 |
| 界面 | 已驳回行显示「重新申请 / 删除申请」；删除前二次确认（`data-confirm` + 页面脚本，无内联 onclick） |
| 权限 | `approval_view`；非申请人 404；非驳回状态的操作被忽略（重新申请不生效、隐藏不生效） |

## 三、测试

- 驳回单重新申请：新单 pending、字段/部门复制、`resubmit` 记录含原单号；
- 隐藏：列表不再显示该单、其它单不受影响、详情仍 200、DB 数据保留；
- 守卫：非驳回不能重新申请 / 隐藏；非申请人 404；
- 既有 177 项不回归。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/approval/models.py` + `migrations/0006_approval_applicant_hidden.py` | 隐藏标记 |
| `plugins/approval/views.py` / `urls.py` | 重新申请 / 隐藏视图与路由；列表过滤 |
| `plugins/approval/services.py` | `submit(..., action=)` 支持 resubmit 留痕 |
| `approval/approval_list.html` | 行内操作 + 二次确认脚本 |
| `approval/approval_detail.html` | 流转记录显示「重新申请」 |
| `plugins/approval/tests_v155.py` | 新增 3 项 |
| `locale/en/LC_MESSAGES/django.po` / `roadmap.md` / `README.md` | 同步 |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 新增 `approval/0006_approval_applicant_hidden`；`makemigrations --check` 干净 |
| 全量单测 | **180 项通过**（基线 177 + 新增 3） |
| Docker 重建 | `docker compose up -d --build` 成功，entrypoint 已执行迁移 |
| 冒烟 | 请假单被 HR 经理驳回 → 列表出现「重新申请 / 删除申请」→ 重新申请生成新待审批单 → 删除后原单不再显示、新单仍在 |
| 守卫 | 非驳回不可重新申请 / 隐藏；非申请人 404；隐藏后数据与详情保留（单测覆盖） |
| 数据清理 | 冒烟产生的审批单已删除 |
