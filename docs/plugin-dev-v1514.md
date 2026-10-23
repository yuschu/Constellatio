# 插件开发文档：v1.5.14 报销金额与用章附件

> 关联插件：approval（动态表单 / 附件下载）、plugin_host（MEDIA 配置）、deploy（media 卷）
> 版本：v1.5.14 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（172 项测试全绿 + 迁移 0005 + Docker 重建 + 上传下载冒烟）

## 一、需求

发起审批的两处调整：

1. **报销**：增加「金额」输入框，必填（`*`）；
2. **用章**：原「用章文件及用途」拆分为「**用章文件***」（必须上传附件）与「用途」；
3. 附件需可下载查看（仅相关人可见）。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 报销金额 | `ExpenseForm.amount`：`DecimalField(required=True, max_digits=12, decimal_places=2, min_value=0)`，界面 `type=number step=0.01 min=0`；落库到既有 `Approval.amount`，同时写入 `form_data['amount']` |
| 用章文件 | `SealForm.seal_file`：`FileField(required=True)`，允许 `pdf/doc/docx/xls/xlsx/png/jpg/jpeg`，单文件 ≤ 10MB；落库到新增 `Approval.attachment` |
| 用途 | `SealForm.purpose`：可选 textarea，写入 `form_data['purpose']` |
| 表单编码 | 发起页 `<form enctype="multipart/form-data">`；视图把 `request.FILES` 传给表单 |
| 附件存储 | `MEDIA_ROOT = BASE_DIR/media`，`upload_to='approval_attachments/%Y/%m/'`；**不做公开静态目录** |
| 附件下载 | `GET /plugins/approval/<id>/attachment/`：申请人 / 审批人 / 会签人 / 抄送人 / `approval_view` 可下载；其余 302；只返回自身附件 |
| 详情展示 | 动态字段显示文件名与用途；有附件时增加「附件 → 下载附件」行；金额单独展示 `￥` |
| 迁移 | 新增 `approval/0005_approval_attachment`（仅加列，非破坏性） |
| 部署 | compose 增加 `media_data:/app/media` 卷，容器重建不丢附件 |

## 三、测试

- 报销：缺金额不落库；填 `288.50` 后 `amount` 与 `form_data` 一致、详情显示金额；
- 用章：缺文件不落库；上传 pdf 后落盘、`form_data['seal_file']` 为文件名、详情有下载入口；申请人下载 200；无关人员 302；
- 用章：`.exe` 被拒绝，不落库；
- 既有 169 项不回归。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/approval/models.py` + `migrations/0005_approval_attachment.py` | 新增 attachment 字段 / 迁移 |
| `plugins/approval/forms.py` | 报销金额、用章文件 + 用途、文件校验 |
| `plugins/approval/views.py` | 接收 FILES、落库 amount/attachment、附件下载视图 |
| `plugins/approval/urls.py` | 附件下载路由 |
| `approval/approval_form.html` | multipart 表单 |
| `approval/approval_detail.html` | 金额 / 附件下载行 |
| `plugins/approval/tests_v155.py` | 新增 3 项测试 |
| `plugin_host/settings.py` / `docker-compose.yml` | MEDIA_ROOT + media 卷 |
| `locale/en/LC_MESSAGES/django.po` | 用章文件 / 用途 / 附件 / 下载附件 / 文件大小提示 |
| `docs/plugin-dev-v155.md` / `roadmap.md` / `README.md` | 同步 |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 新增 `approval/0005_approval_attachment`；`makemigrations --check` 干净 |
| 全量单测 | **172 项通过**（基线 169 + 新增 3） |
| Docker 重建 | `docker compose up -d --build` 成功，entrypoint 已执行迁移，`constellatio-web-1` 运行 |
| 报销冒烟 | 表单含金额 `type=number` 必填；缺金额 200 拦截；填 `88.50` 提交成功；列表/详情显示 `￥88.50` |
| 用章冒烟 | 表单含「用章文件」文件框 + 「用途」；缺附件 200 拦截；上传 `contract.pdf` 成功；详情显示「下载附件」，下载 200 且内容为 PDF；未上传者与无关人员不可下载（单测覆盖） |
| 数据清理 | 冒烟产生的测试审批单已删除 |
