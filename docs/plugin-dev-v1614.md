# 插件开发文档：v1.6.14 用户管理操作项按钮化

> 关联：user（用户管理）、themes（按钮变体）
> 版本：v1.6.14 · 文档日期：2026-10-24
> 状态：**✅ 已实现并部署**（用户模块 25 项测试通过；全量 235/237，见下）

## 一、需求

1. 用户管理操作项全部改为实体按钮，统一宽高 / 圆角 / 内边距、间距均匀、同行对齐：
   - 编辑：白底蓝字常规按钮；
   - 冻结权限：蓝色常规按钮；
   - 禁用：红色危险按钮；
2. admin 超管行不展示任何操作按钮，只保留灰色提示「超管（不可操作）」。

## 二、设计口径

| 项 | 决策 |
|---|---|
| 编辑 | 文字链接 → `r-btn r-btn--ghost r-btn--action`（新增白底蓝字变体，两套主题各实现） |
| 冻结 / 解冻 / 启用 | `r-btn r-btn--action`（主题主色蓝） |
| 禁用 | `r-btn r-btn--danger r-btn--action`（红色，v1.6.11 定义） |
| 统一尺寸 | 新增 `.r-btn--action`：`min-width:5.5rem` + `inline-flex` 居中，短词按钮同宽、高度一致 |
| 布局 | 单元格内 `d-flex align-items-center gap-2`；表单 `m-0`；操作列 `text-nowrap`，同行等高对齐 |
| 超管行 | 仅 `text-muted` + `font-size:.75rem` 文案，无任何按钮 |
| 交互 | 冻结 / 禁用原有确认弹窗、POST action、权限判断与状态机全部不变 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/user/templates/user/user_list.html` | 编辑按钮化；冻结 / 禁用 / 启用加 `r-btn--action`；禁用红色 |
| `themes/corporate-clean/.../corporate-clean.css` | `.r-btn--ghost`、`.r-btn--action` |
| `themes/risograph/.../risograph.css` | `.r-btn--ghost`、`.r-btn--action` |
| 文档 | 本文件 + roadmap / README / constraints |

## 四、测试与部署（2026-10-24）

| 项 | 结果 |
|---|---|
| 用户模块测试 | **25 项通过** |
| 全量测试 | **235 / 237 通过**；2 项失败为 `plugins.attendance.tests.AttendanceRecordFilterTests` 的筛选用例：测试数据签到时间 09:30 晚于运行时刻 00:0x，默认时间范围（当月 1 日 → 当前时刻）排除当天记录导致（既有的跨日 / 时钟边界问题，与本次 UI 改动无关） |
| Docker 部署 | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
