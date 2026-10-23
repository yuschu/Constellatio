# 插件开发文档：v1.5.13 角色弹窗居中浮出

> 关联插件：structure（角色成员弹窗）
> 版本：v1.5.13 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（169 项测试全绿 + Docker 重建 + 冒烟）

## 一、需求

角色成员弹窗改为**居中浮出**：垂直/水平居中，出现时带轻微缩放淡入动效，关闭时自然回落。

## 二、实现

| 项 | 决策 |
|---|---|
| 居中 | Bootstrap `modal-dialog-centered`（水平 + 垂直居中） |
| 浮出动效 | 页面内 scoped CSS：`#roleModal .modal-dialog` 初始 `translateY(14px) scale(.96)` + `opacity:0`，`.show` 时回到 `none/1`，`transition` 180ms |
| 可访问性 | `prefers-reduced-motion: reduce` 时关闭动效，直接显示 |
| 兼容 | 保留 `modal-dialog-scrollable`（成员多时弹窗内部滚动）；不引入主题 CSS 改动、不新增 JS |
| 数据/权限 | 无变化：无新表、无迁移、无权限调整 |

## 三、验收

- 弹窗在视口水平、垂直居中；
- 打开时从下方 14px、96% 缩放淡入到正常大小，关闭时回落；
- 成员较多时弹窗内容区滚动，不撑破视口；
- 减少动效偏好下无动画。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `templates/structure/overview.html` | `modal-dialog-centered` + scoped 动效 CSS |
| `plugins/structure/tests.py` | 断言居中类与动效选择器 |
| `docs/roadmap.md` / `README.md` | 同步 |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **169 项通过**（断言新增到既有角色卡片测试） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 冒烟 | 页面含 `modal-dialog-centered`、`#roleModal .modal-dialog`、`translateY(14px) scale(.96)`、`transform .18s ease`、`prefers-reduced-motion: reduce`，且保留 `modal-dialog-scrollable` |
