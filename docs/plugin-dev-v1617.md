# 插件开发文档：v1.6.17 考勤卡片收紧 / 按钮同行 / 插件改名

> 关联：attendance（考勤看板 + 插件元信息）
> 版本：v1.6.17 · 文档日期：2026-10-24
> 状态：**✅ 已实现并部署**（rbac / attendance / user 63/65，2 项既有跨日时钟边界；全量 235/237）

## 一、需求

1. 今日状态、本月统计卡片去掉多余纵向留白，收紧卡片高度；
2. 签到、签退按钮与签到类型输入框同一行并排，按钮尺寸统一、间距均匀，减少底部空行；
3. 插件名「考勤打卡」改为「考勤」；
4. 字段、数据、功能不变。

## 二、设计口径

| 项 | 决策 |
|---|---|
| 卡片高度 | 两卡去掉 `h-100`，行改 `align-items-start`，卡片高度随内容收紧（不再互相拉伸留白） |
| 按钮同行 | 原来的两个 `<form>` 合并为一个表单：`签到类型 select + 签到 + 签退` 置于 `d-flex flex-wrap align-items-end gap-2`；两个按钮共用 `r-btn--action`（min-width 5.5rem、内容居中），同行等高、等距 |
| 提交语义 | 同一表单两个 submit 按钮 `name=action value=in/out`，视图按 `request.POST['action']` 分支，行为与原来一致；禁用态保留 |
| 间距 | 控件区上边距 `mt-4` → `mt-3`，去掉按钮的 `mt-2`，减少底部空行 |
| 插件改名 | `PluginMeta.title` 与菜单 label 由「考勤打卡」改为「考勤」；权限码 label（`attendance_check`）与迁移不变，插件版本 0.6.0 不变 |
| 测试 | `plugin_host.tests_rbac` 菜单断言由「考勤打卡」改为「考勤」 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/attendance/apps.py` | 插件标题 / 菜单名改「考勤」 |
| `plugins/attendance/templates/attendance/attendance_dashboard.html` | 去 `h-100`；合并表单，按钮同行 |
| `plugin_host/tests_rbac.py` | 菜单断言更新 |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移、无 i18n 新增（「考勤」文案 v1.6.16 已翻译）。

## 四、测试与部署（2026-10-24）

| 项 | 结果 |
|---|---|
| rbac / attendance / user | 63 / 65 通过；2 项为既有 `AttendanceRecordFilterTests` 跨日时钟边界（签到 09:30 晚于运行时刻 00:2x） |
| 全量 | 235 / 237（同上 2 项） |
| Docker 部署 | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
