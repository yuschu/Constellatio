# 插件开发文档：v1.6.19 部门操作按钮配色调整

> 关联：user（部门管理）
> 版本：v1.6.19 · 文档日期：2026-10-24
> 状态：**✅ 已实现并部署**

## 一、需求

部门管理操作列：修改改为白底蓝字按钮，停用改为蓝色按钮；物理删除保持红色危险按钮。

## 二、设计口径

| 操作 | 按钮 |
|---|---|
| 修改 | `r-btn r-btn--ghost r-btn--action`（白底蓝字蓝边，v1.6.14 变体） |
| 停用 | `r-btn r-btn--action`（主题主色蓝） |
| 物理删除 | `r-btn r-btn--danger r-btn--action`（红色，不变） |

- 三个按钮统一 `r-btn--action`（min-width 5.5rem、内容居中），同行等距对齐；
- 未启用部门行仅保留「修改」（ghost）；
- 确认弹窗、POST action、权限与软 / 硬删除逻辑不变。

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/user/templates/user/department_list.html` | 修改 / 停用按钮 class 调整 |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移、无 Python / 样式新增变化。

## 四、部署结果（2026-10-24）

| 项 | 结果 |
|---|---|
| 模板语法 | 解析校验通过 |
| Docker | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
| 自动化测试 | 纯模板 class 调整，未重复跑全量 |
