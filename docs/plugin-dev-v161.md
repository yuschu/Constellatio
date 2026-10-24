# 插件开发文档：v1.6.1 图表引擎运行时开关 + 留痕链统计图表

> 关联：workspace（开关 UI / CLI）、plugin_host.charts、blockchain（统计看板）
> 版本：v1.6.1 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（220 项测试全绿 + Docker 重建；待收尾 tag / push）

## 一、需求

1. **图表插件开关**：图表引擎进入插件开关体系，可在「插件开关」页 / `manage.py plugin_switch` 运行时启停，**即时生效**；
2. **留痕链统计图表**：留痕链列表新增统计看板（按日 × 来源插件），与 v1.6 `ChartRenderer` 契约一致，停用图表 / 无数据时降级表格。

## 二、设计口径（契约）

### 2.1 图表引擎作为「Provider 插件」

- 图表 Provider 仍不是 Django app（无模型、无迁移、无 URL），但以 **`charts` 键注册进 `PLUGIN_REGISTRY`**：
  - 由容器 `plugin_host/apps.py::ready()` 注册，`title=图表引擎`、`menus=[]`、`permissions=[]`、`urls=None`；
  - 因此自动出现在 workspace 插件开关列表，与业务插件同一开关语义与上链动作。
- 开关存储：复用 `workspace.PluginSwitch(app_key='charts')`；**DB 优先，无记录视为启用**。
- 生效链路（`plugin_host.charts.get_active_chart()`，每次请求读取，无需重启）：

| 判定顺序 | 条件 | 结果 |
|---|---|---|
| 1 | `OA_CHARTS` ∈ `{'' , none, off, false, 0}` | 停用（仅表格） |
| 2 | `PluginSwitch(app_key='charts').enabled = False` | 停用（仅表格） |
| 3 | `OA_CHARTS` 未知 / Provider 不可用 | 降级（仅表格，warning） |
| 4 | 其余 | 返回 Provider 渲染器 |

- 切换动作写 `PluginSwitch` 并发 `plugin_toggled` 信号（与其它插件一致，自动上链，`payload=charts:<bool>`）；
- workspace 开关页对 `charts` 显示风险提示（停用 → 所有图表降级为表格）；
- CLI 兜底：`manage.py plugin_switch list|on charts|off charts`。

### 2.2 留痕链统计接口

`GET /plugins/blockchain/stats/?days=30`（权限 `blockchain_view`，与列表同源）

| 参数 | 说明 |
|---|---|
| `days` | 1–90 的整数，默认 30；非整数或越界 → `400 {"error":"invalid_days"}` |

响应：

```json
{
  "days": 30,
  "range": {"start": "2026-09-24", "end": "2026-10-23"},
  "dates": ["09-24", "…", "10-23"],
  "series": [{"key": "user", "label": "用户与组织", "data": [3, 0, "…"]}],
  "totals": {"records": 120},
  "payload": {"engine": "echarts", "option": {"…": "…"}}
}
```

- 聚合口径：`BlockchainRecord.created_at` 按服务器时区（`TIME_ZONE`）落到自然日，按「日 × 来源插件」计数；展示名取 `PLUGIN_REGISTRY[plugin].title`，未知 key 原样输出；
- `series` 按窗口内记录总数倒序，`data` 与 `dates` 等长（无记录补 0）；
- `payload` 由当前 `ChartRenderer` 生成；图表停用时为 `null`（数据仍可查询）。

### 2.3 页面与降级

- `/plugins/blockchain/` 新增「留痕统计」卡：时间窗选择（近 7 / 30 / 90 天）+ 图表容器 + 服务端渲染降级表格（日期 × 插件 + 合计）；
- 图表可用：前端 `fetch(stats)` → `window.oaChartRender(el, payload)`，表格隐藏；
- 图表停用 / 脚本缺失 / fetch 失败 / 窗口内无记录：显示降级表格或「该时间范围内暂无留痕记录」，无未捕获异常；
- 统计与留痕列表同源（同一张 `blockchain_record`），不改变链校验与上链逻辑。

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugin_host/apps.py` | 注册 `charts` Provider 插件元信息 |
| `plugin_host/charts.py` | `get_active_chart()` 接入 DB 运行时开关 |
| `plugins/workspace/views.py` | `charts` 风险提示 |
| `plugins/workspace/management/commands/plugin_switch.py` | `list` 正确显示 Provider 开关状态 |
| `plugins/blockchain/views.py` / `urls.py` | 统计聚合 + `/stats/` JSON |
| `plugins/blockchain/templates/blockchain/blockchain_list.html` | 统计看板 + 降级表格 |
| `plugins/blockchain/tests.py`、`plugin_host/tests_charts.py`、`plugins/workspace/tests.py` | 新增开关 / 统计 / 降级用例 |
| `locale/en/.../django.po` + `compile_mo.py` | 新文案英文翻译 |
| `docs/plugin-dev-v16.md` / `docs/roadmap.md` / `README.md` | 同步 |

**无新表、无迁移**（复用 `workspace_pluginswitch`）。

## 四、验收口径

1. 开关即时生效：关 → 考勤页 / 留痕页 200 且无图表脚本，stats `payload=null`；开 → 恢复；
2. 开关动作上链（`plugin_toggled charts`）；CLI 与 UI 状态一致；
3. 留痕统计与 `blockchain_record` 聚合一致（按日 / 插件 / 窗口）；
4. 非法 `days` → 400；无权限 → 与列表一致的 302；
5. 新增单测全绿、既有测试不回归；`check` / `makemigrations --check` 干净；
6. Docker 重建后静态资源与页面正常。

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 无新迁移（`makemigrations --check` 干净；复用 `workspace_pluginswitch`） |
| 全量单测 | **220 项通过**（v1.6 基线 204 + 新增 16：Provider 插件注册 / DB 开关 / UI 与 CLI / 留痕统计 / 窗口 / 降级） |
| 开关即时生效 | 开关页与 CLI 均写 `PluginSwitch(app_key='charts')`；关闭后考勤页、留痕页 200 且无图表脚本，两处 stats `payload=null`；重新开启即恢复（无需重启） |
| 上链 | 切换发 `plugin_toggled`（`payload=charts:<bool>`），与其它插件同一上链路径 |
| 留痕统计 | `/plugins/blockchain/stats/` 按日 × 来源插件聚合；窗口 `days=2/7` 过滤旧记录验证通过；`series` 之和 = `totals.records`；`days` 非法（0 / 91 / abc）→ 400 |
| 权限 | 统计接口与列表同源 `blockchain_view`；无权限 302 |
| 降级 | 图表开关 off / `OA_CHARTS=none` / 无数据：留痕页与考勤页均降级表格，无未捕获异常 |
| Docker 重建 | `docker compose up -d --build` 成功；容器内 `charts` 已注册、开关默认 on、Provider `echarts` 加载；`/static/vendor/echarts.min.js` 200 |

> 说明：`plugin_switch list` 已能正确显示 Provider 插件（`charts`）状态；图表开关关闭不影响统计数据接口与留痕链校验。
