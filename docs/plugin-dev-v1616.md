# 插件开发文档：v1.6.16 考勤 / 签到详情页面优化

> 关联：attendance（考勤看板 / 签到详情）、charts（复用）
> 版本：v1.6.16 · 文档日期：2026-10-24
> 状态：**✅ 已实现并部署**（考勤模块 23/25，2 项跨日时钟边界既有问题；全量 235/237）

## 一、需求

1. 考勤打卡页标题改为「考勤」；保留左右两卡（今日状态 / 本月统计），下方新增考勤图表卡片（月度出勤 / 迟到分布）；原控件保留、按钮与全站统一；
2. 签到详情筛选区：开始时间 → 结束时间 → 签到状态 → 签到类型 → 部门 → 姓名或账号 → 筛选 → 重置，单行横向排布，窄屏自动换行；指标卡与月度看板保留；控件尺寸与全站筛选区一致。

## 二、设计口径

### 考勤看板

| 项 | 决策 |
|---|---|
| 标题 | 页面 `<title>` 与 h2 改「考勤」（菜单名仍为插件「考勤打卡」，未改插件元信息） |
| 布局 | `row g-4` 今日状态 `col-lg-5` / 本月统计 `col-lg-7`（`h-100` 等高），下方 `r-card mt-4` 图表卡 |
| 图表 | `_month_stats(month_start, user=request.user)` 聚合个人本月逐日状态（正常 / 迟到 / 早退 / 缺卡 / 补卡），`ChartRenderer` 生成堆叠柱；图表停用时表格展示各状态天数 |
| 数据复用 | 复用 v1.6 月度统计函数，新增 `user=` 过滤参数（管理接口行为不变） |
| 按钮 / 控件 | 签到类型下拉、签到 / 签退按钮沿用 `r-input` / `r-btn` 与禁用态 |

### 签到详情筛选

| 项 | 决策 |
|---|---|
| 单行排布 | 表单 `d-flex flex-wrap align-items-end gap-2`；各字段 `flex:1 1 Nrem; min-width` 自适应，按钮 `flex:0 0 auto` |
| 顺序 | 开始时间 → 结束时间 → 状态 → 类型 → 部门 → 姓名/账号 → 筛选 → 重置 |
| 窄屏 | flex-wrap 自动换行；控件宽度随容器收缩，不溢出 |
| 其余 | 4 指标卡、月度看板、补卡表单结构不变 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/attendance/views.py` | `_month_stats` 支持 `user`；看板传递个人月度图表 payload / 状态合计 |
| `plugins/attendance/templates/attendance/attendance_dashboard.html` | 标题、等高卡片、图表卡 + 降级表格 + 图表脚本 |
| `plugins/attendance/templates/attendance/attendance_records.html` | 筛选区单行自适应布局 |
| `locale/en/.../django.po` | 新增「考勤」「考勤图表」「天数」 |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移。

## 四、测试与部署（2026-10-24）

| 项 | 结果 |
|---|---|
| 考勤模块测试 | 23 / 25 通过；2 项失败为既有 `AttendanceRecordFilterTests` 跨日时钟边界（签到 09:30 晚于运行时刻 00:1x），与本次改动无关 |
| 全量测试 | 235 / 237（同上 2 项） |
| 翻译 | `compile_mo.py` 已编译 |
| Docker 部署 | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
