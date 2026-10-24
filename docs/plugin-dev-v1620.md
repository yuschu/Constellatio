# 插件开发文档：v1.6.20 部门状态徽标绿色与防折行

> 关联：user（部门管理）
> 版本：v1.6.20 · 文档日期：2026-10-24
> 状态：**✅ 已实现并部署**

## 一、需求

部门管理状态列「启用」徽标放大显示、不挤成两行；启用改为绿色。

## 二、设计口径

| 项 | 决策 |
|---|---|
| 状态列 | `<td>` 加 `text-nowrap`，避免「启用」在窄列中被按字折行，列宽随徽标自动撑开 |
| 启用 | 徽标加 `r-badge--green`（两套主题均有定义：Corporate 浅绿底绿字 / Risograph 绿底白字） |
| 停用 | 保持 `r-badge--orange` 不变 |
| 不变 | 状态判断、数据与其它列不变 |

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugins/user/templates/user/department_list.html` | 状态列 `text-nowrap` + 启用绿徽标 |
| 文档 | 本文件 + roadmap / README / constraints |

无新表、无迁移、无 CSS / Python 变化。

## 四、部署结果（2026-10-24）

| 项 | 结果 |
|---|---|
| 模板语法 | 解析校验通过 |
| Docker | `docker compose up -d --build` 成功；`constellatio-web-1` 运行 |
| 自动化测试 | 纯模板调整，未重复跑全量 |
