# 插件开发文档：v1.6.11 部门管理页排版优化

> 关联：user（部门列表 / 新建 / 修改）、themes（卡片 / 表格 / 按钮样式）
> 版本：v1.6.11 · 文档日期：2026-10-23
> 状态：**✅ 已实现并部署**（237 项测试全绿 + Docker 重建）

## 一、需求

部门管理页保持「左表格 + 右表单」分栏，统一卡片样式与留白，表格与表单对齐更规整；功能、字段、交互不变；操作按钮按风险配色（修改蓝 / 停用灰 / 物理删除红）。

## 二、设计口径

| 项 | 决策 |
|---|---|
| 分栏 | `row g-4 align-items-start`：左 `col-lg-8` 表格卡、右 `col-lg-4` 表单卡，两卡顶部对齐；窄屏堆叠 |
| 卡片 | 两侧统一 `r-card`（圆角 / 内边距 / 阴影沿用主题），与工作台一致 |
| 表格 | `r-table r-table--roomy align-middle`：单元格垂直居中；新增宽松内边距（Corporate 0.85rem、Risograph 0.75rem）；表格外层 `table-responsive` 防溢出 |
| 操作列 | 三个表单 `m-0`，按钮置于 `d-flex align-items-center gap-2`，间距均匀；列 `text-nowrap` |
| 按钮配色 | 修改 `r-btn`（主题主色）；停用 `r-btn--plain`（中性）；物理删除新增 `r-btn--danger`（`--r-danger` 红，两主题各实现 hover） |
| 表单 | 字段统一 `d-grid gap-3`；标签 + 控件左对齐、宽度 100%；「创建 / 保存修改」按钮与输入框左对齐；`parent` 下拉补 `r-input` 样式（表单 widget） |
| 留白 | 页头 `mb-4`、卡片间 `g-4`、错误卡 `mb-4`，与工作台一致 |
| 不变 | 表单字段、POST action、权限、软/硬删除流程与确认文案均未改 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/user/templates/user/department_list.html` | 分栏 / 表格 / 操作按钮 / 表单布局重写 |
| `plugins/user/forms.py` | `DepartmentForm.parent` 补 `r-input` widget class |
| `themes/corporate-clean/.../corporate-clean.css` | `.r-btn--danger`、`.r-table--roomy` |
| `themes/risograph/.../risograph.css` | `.r-btn--danger`、`.r-table--roomy` |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移、无视图逻辑变化。

## 四、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| 全量单测 | **237 项通过**（与 v1.6.10 基线一致，无回归） |
| 布局 | 左右分栏顶部对齐；窄屏堆叠；卡片样式统一 |
| 表格 | 表头 / 单元格左对齐、垂直居中；操作三按钮 `gap-2` 等距，修改蓝 / 停用中性 / 删除红 |
| 表单 | 标签、输入、下拉等宽左对齐；创建按钮左对齐；字段间距均匀 |
| Docker 部署 | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
