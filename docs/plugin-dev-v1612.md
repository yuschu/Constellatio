# 插件开发文档：v1.6.12 角色 / 审批 / 待办三页统一排版

> 关联：user（角色管理）、approval（审批中心 / 待我审批）、themes（表格表头）
> 版本：v1.6.12 · 文档日期：2026-10-23
> 状态：**✅ 已实现并部署**（237 项测试全绿 + Docker 重建）

## 一、需求

角色管理、审批中心、待我审批三页统一排版：表格垂直居中 / 表头对齐、宽松行高内边距、状态标签统一、操作控件一致、右上主按钮与标题对齐、窄屏自适应；不改字段 / 数据 / 交互。

## 二、设计口径

| 项 | 决策 |
|---|---|
| 表格通用 | 三页统一 `r-table r-table--roomy align-middle`（v1.6.11 定义的宽松内边距）+ `table-responsive` 包裹；所有 `<th>` 加 `scope="col"`，操作列 `text-nowrap` |
| 表头 | Corporate Clean 表头文字由灰色改为 `var(--r-ink)`（深色、与内容层级区分）；背景 / 分隔线沿用主题 |
| 角色管理 | 权限码改 `d-flex flex-wrap gap-1` 流式换行；操作列「编辑」改 `r-btn`（与部门「修改」一致）；页头 `flex-wrap gap-2` |
| 审批中心 | 状态标签：已通过 `r-badge--green`、待审批 `r-badge--blue`、已驳回 `r-badge--orange`、草稿默认；修复操作列 `td.d-flex` 破坏表格布局的问题，改为单元格内 `div.d-flex` 包裹；行高 / 内边距统一 |
| 待我审批 | 待办角标改 `r-badge--blue`，与标题同排（`flex-wrap gap-2`）；「去审批」`r-btn` + 操作列 `text-nowrap`，同行按钮上下对齐 |
| 页头 | 三页统一 `d-flex justify-content-between align-items-center flex-wrap gap-2 mb-4`；右上按钮均为 `r-btn` |
| 卡片 | 沿用 `r-card` 圆角 / 阴影 / 内边距，与工作台、部门管理一致 |
| 不变 | 字段、查询、状态流转、二次确认脚本、跳转与权限全部未改 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/user/templates/user/role_list.html` | 表格 / 权限码 / 操作按钮 / 页头 |
| `plugins/approval/templates/approval/approval_list.html` | 表格 / 状态标签 / 操作区结构 / 页头 |
| `plugins/approval/templates/approval/approval_pending.html` | 表格 / 角标 / 操作按钮 / 页头 |
| `themes/corporate-clean/.../corporate-clean.css` | 表头文字颜色改深色 |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移、无视图逻辑变化。

## 四、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| 全量单测 | **237 项通过**（无回归） |
| 三页表格 | 垂直居中、表头左对齐一致、宽松内边距、`table-responsive` 窄屏可横向滚动 |
| 角色页 | 权限码 flex 换行不溢出；编辑按钮与部门页「修改」同款 |
| 审批页 | 状态标签四态配色统一；操作列结构修复后列对齐正常 |
| 待办页 | 待办角标与标题协调；去审批按钮同行对齐 |
| Docker 部署 | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
