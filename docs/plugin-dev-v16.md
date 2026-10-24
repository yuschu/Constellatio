# 插件开发文档：v1.6 图表插件化 + ECharts

> 关联：plugin_host（容器）/ attendance（首个业务看板）
> 版本：v1.6 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（204 项测试全绿 + Docker 重建；待收尾 tag / push）

## 一、需求

1. **图表引擎插件化**：容器提供统一 `ChartRenderer` 接口，图表引擎可按 Provider 替换；
2. **ECharts Provider**：本地静态资源 `static/vendor/echarts.min.js`（不依赖 CDN）；
3. **考勤统计接口**：`/plugins/attendance/stats/?month=YYYY-MM` 返回月度 JSON（按日 / 按人）；
4. **签到详情月度看板**：管理岗 `/plugins/attendance/records/` 内嵌 ECharts 看板；
5. **停用降级**：图表引擎停用 / 资源缺失 / 前端初始化失败时，页面降级为表格且不报错。

## 二、设计口径（契约）

### 2.1 Provider 发现（与主题同模型）

- 图表引擎 = 目录 `charts/<key>/` + 清单 `chart.json`，**不是 Django app**，不挂 `INSTALLED_APPS`、不写迁移；
- `key` 取自目录名（与主题一致）；设置项 `OA_CHARTS` 选择默认引擎（环境变量同名）；
- 清单必填字段：

| 字段 | 含义 |
|---|---|
| `name` | 展示名（如 `ECharts`） |
| `version` | Provider 版本（如 `5.5.1`） |
| `renderer` | Python 渲染器类路径（`charts.echarts.renderer.EChartsRenderer`） |
| `static` | 相对 Provider 根目录的静态目录（进 `STATICFILES_DIRS`） |
| `asset` | 相对 `static` 的引擎脚本（进页面 `<script src>`） |

- 选填 `adapter`：相对 `static` 的适配脚本，负责把统一 `payload` 渲染成该引擎的图表；
- 启动时扫描清单；清单不可解析 / 字段缺失 / 渲染器不是 `ChartRenderer` 子类 → `ImproperlyConfigured`（失败要吵，不静默）；
- Provider 静态目录整体加入 `STATICFILES_DIRS`，因此**引擎静态文件名必须在全站唯一**（当前约定：库放 `vendor/`、适配器放 `js/`）。

### 2.2 ChartRenderer 契约

```python
class ChartRenderer:
    meta: ChartMeta

    def option(self, *, categories=None, series=None, title='', kind='cartesian',
               compact=False) -> dict: ...
    def payload(self, *, categories=None, series=None, title='', kind='cartesian',
                compact=False, link='', alert=False) -> dict
        # {'engine': key, 'option': {...}, 'link': ..., 'alert': bool}
        # option 必须是 JSON 可序列化
```

> v1.6.2 扩展 `kind`（cartesian / pie / gauge）、`compact`（迷你图）、`link`（点击跳转）、`alert`（告警色），详见 `docs/plugin-dev-v162.md`。

- `categories`：类目轴（字符串列表）；
- `series`：`[{'key','name','data','type'?}]`，`type` 缺省 `bar`；`name` 已按当前语言本地化；
- 容器只认 `payload`，业务视图不 import 任何具体引擎；
- `script_url` / `adapter_url` 由 `django.templatetags.static.static` 解析，兼容 `collectstatic`。

### 2.3 ECharts Provider（`charts/echarts/`）

| 项 | 决策 |
|---|---|
| 引擎 | Apache ECharts 5.5.1（Apache-2.0），文件 `charts/echarts/static/vendor/echarts.min.js`（→ `/static/vendor/echarts.min.js`） |
| 适配器 | `charts/echarts/static/js/echarts.js`，注册 `window.oaChartRender(el, payload)`（`echarts.init` + `setOption` + resize） |
| Option | 类目 x 轴 / 数值 y 轴 / `stack` 堆叠柱 / tooltip 轴触发 / legend 底部 |
| 数据来源 | 服务端生成 option，前端只做渲染——换引擎不需要改业务视图 |

### 2.4 运行时选择与降级（硬要求）

> v1.6.1 起：图表引擎注册为 Provider 插件（`PluginSwitch(app_key='charts')`），**插件开关页 / `manage.py plugin_switch` 可运行时启停并上链**；DB 开关优先于 `OA_CHARTS` 的「启用」语义（`OA_CHARTS` 的停用值仍然生效）。详见 `docs/plugin-dev-v161.md`。

| 场景 | 行为 |
|---|---|
| `OA_CHARTS=echarts`（默认）且开关 on | 页面注入引擎脚本 + 适配器 + 图表容器；stats JSON 带 `payload` |
| `OA_CHARTS=` / `OA_CHARTS=none` / `OA_CHARTS=off`，或插件开关 off | 视为停用：不注入脚本与容器，**只渲染表格**；stats 仍返回原始数据（`payload=null`） |
| Provider 未知（拼写错误） | 记 warning 并降级（不 500）——停用/误配不阻断业务页 |
| 浏览器无 `echarts` / 适配器缺失 / fetch 失败 | 前端移除容器、显示服务端表格（`hidden` 解除），不抛未捕获异常 |
| 无数据 | 表格显示「本月暂无考勤记录」，前端显示空态（无数据月份） |

### 2.5 考勤统计接口

`GET /plugins/attendance/stats/`（权限 `attendance_report_view`，与菜单/页面同源）

| 参数 | 说明 |
|---|---|
| `month` | `YYYY-MM`；缺省当前月；非法 → `400` + `{"error":"invalid_month"}` |
| `department` | 可选部门 id；非数字忽略（与签到详情筛选口径一致） |

响应：

```json
{
  "month": "2026-10",
  "range": {"start": "2026-10-01", "end": "2026-10-31"},
  "dates": ["10-01", "10-02"],
  "series": [{"key": "late", "label": "迟到", "data": [3, 1]}],
  "totals": {"records": 42, "normal": 20, "late": 3, "early": 1, "missing": 12, "makeup": 6},
  "users": [{"username": "u1", "name": "张三", "normal": 2, "late": 1, "early": 0, "missing": 0, "makeup": 0}],
  "payload": {"engine": "echarts", "option": {"xAxis": {"data": ["10-01", "10-02"]}}}
}
```

- 统计口径 = `Attendance` 记录本身（`date__range` + 可选部门），与签到详情列表同源；每日数据是当月**实际存在的记录**按 `status` 聚合，缺日补 0；
- 一天一卡由模型 `unique_together` 保证，因此按日/按人聚合不会重复计数；
- `users` 按记录数倒序、账号升序，最多返回当月有记录的全部人。

## 三、改动面

| 文件 | 动作 |
|---|---|
| `plugin_host/charts.py` | 新增：发现 / 元信息 / `ChartRenderer` / 运行时选择与降级 |
| `charts/echarts/chart.json`、`renderer.py`、`static/vendor/echarts.min.js`、`static/js/echarts.js` | 新增：ECharts Provider（本地资源） |
| `plugin_host/settings.py` | `OA_CHARTS` + Provider 静态目录并入 `STATICFILES_DIRS` |
| `plugin_host/context_processors.py` | 注入 `chart`（停用为 `None`） |
| `plugins/attendance/views.py` | `attendance_stats`（JSON）+ 签到详情月度表数据与月份参数 |
| `plugins/attendance/urls.py` | `stats/` 路由 |
| `plugins/attendance/templates/attendance/attendance_records.html` | 月度看板卡 + 降级表格 |
| `plugins/attendance/tests.py` | 新增统计/看板/降级/契约用例 |
| `locale/en/.../django.po` + `tools/compile_mo.py` | 新文案英文翻译 |
| `docs/roadmap.md` / `docs/development-guide.md` / `README.md` / 快照索引 | 文档同步 |

**无新表、无迁移**（仅查询既有 `attendance_attendance`）。

## 四、验收口径

1. 图表数据与打卡记录一致：same filters 下 JSON 聚合 = ORM 聚合；
2. 停用图表 Provider（`OA_CHARTS=''`）后签到详情页 200，只有表格、无图表脚本，stats 返回 `payload=null`；
3. 未知 Provider 键不 500；
4. 新增单测全绿、既有 184 项不回归；`check` / `makemigrations --check` 干净；
5. `docker compose up -d --build` 后 `/static/vendor/echarts.min.js` 可访问（collectstatic 已收），签到详情页含看板。

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 无新迁移（`makemigrations --check` 干净；未改模型） |
| 全量单测 | **204 项通过**（v1.5.18 基线 184 + 新增 20：图表契约 / 清单校验 / 统计 JSON / 权限 / 降级 / 页面） |
| 数据一致性 | `_month_stats` 直接聚合 `Attendance`（状态取自模型 `compute_status`），`series` 之和 = `totals.records` = 记录数 |
| 停用降级 | `OA_CHARTS=''｜none｜off`：页面 200、无脚本、表格可见；stats 返回 `payload=null`；未知 Provider 仅 warning 不 500 |
| 本地资源 | `charts/echarts/static/vendor/echarts.min.js`（ECharts 5.5.1，1,030,855 B，sha256 `e84270bd…73a3cf`）；Docker 内 `/static/vendor/echarts.min.js` 200 |
| Docker 重建 | `docker compose up -d --build` 成功；`constellatio-web-1` 新代码启动，容器内 `OA_CHARTS=echarts`、Provider 发现与渲染器加载正常 |
| 测试调整 | `plugin_host/tests.py::test_active_theme_dirs` 的静态目录断言纳入 Provider 目录（v1.6 预期变化） |

> 说明：签到详情页的月度看板由服务端渲染降级表格 + 前端 fetch 覆盖；图表引擎停用、脚本缺失、fetch 失败或无数据时均回落到表格，无未捕获异常。
