# 插件开发文档：v1.6.2 工作台图表化大盘

> 关联：plugin_host（工作台）、charts（渲染契约扩展）、approval / attendance / blockchain / user / workspace（数据源）
> 版本：v1.6.2 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（231 项测试全绿 + Docker 重建；待收尾 tag / push）

## 一、需求

1. 工作台首屏改为「指标数字 + 迷你图表」的看板（4 卡：待我审批 / 考勤概况 / 流程发起 / 插件状态）；
2. 流程趋势大盘：近 30 天（按筛选联动）多曲线，保留快捷发起按钮组；
3. 插件分布饼图 + 组织人员柱状图（管理员专属）；
4. 时间筛选器（今日 / 本周 / 本月）联动全部图表；告警色；移动端自适应；
5. 员工视图只保留个人数据（待办 / 考勤 / 自己发起），隐藏全局与组织图表。

## 二、数据口径（契约）

### 2.1 时间范围（`?range=`）

| key | 含义 | 窗口 | 大盘 X 轴 |
|---|---|---|---|
| `today` | 今日 | 今天 00:00 → 现在 | 24 个小时桶 |
| `week` | 本周 | 近 7 天（含今天） | 7 个日桶 |
| `month`（默认） | 本月 | **近 30 天（含今天）**，与「近 30 天大盘」同口径 | 30 个日桶 |

- 非法值回退 `month`；筛选为普通 GET 链接，服务端重算（无前端状态）；
- 「流程发起 / 待办完成 / 留痕活跃」等统计均按该窗口；「待我审批」的**当前待办数**为全量实时值，不受窗口影响。

### 2.2 角色分流

| 区块 | 管理员（`workspace_manage` 或超管） | 员工 |
|---|---|---|
| 待我审批 | 个人待办 + 窗口内审批完成率 | 同左（需 `approval_approve`，沿用 v1.5.15 L3 隐藏口径） |
| 考勤概况 | 个人打卡趋势 + 今日状态 | 同左 |
| 流程发起 | **全员**按类型计数 | **本人**按类型计数 |
| 插件状态 | 已启用 / 注册总数 + 健康度 | 隐藏 |
| 流程趋势大盘 | 全员按类型 | 本人按类型 |
| 插件分布饼图 | ✅（留痕活跃） | 隐藏 |
| 组织人员柱状图 | ✅ | 隐藏 |

### 2.3 指标与图表

| 区块 | 数据源 | 图表 |
|---|---|---|
| 待我审批 | `Approval`：`approver=me` 或未签会签人；窗口内 `approver=me` 的完成率 | 环形进度（gauge，完成率 %） |
| 考勤概况 | `Attendance`：本人窗口内逐桶记录数；今日状态取 `_attendance_today` | 迷你折线 |
| 流程发起 | `Approval` 五类（请假 / 报销 / 用章 / 外出 / 加班）按类型计数；窗口 | 迷你柱状 |
| 插件状态 | `PLUGIN_REGISTRY` 总数 + `get_enabled_plugins()` + `charts` 开关 | 环形进度 |
| 流程趋势大盘 | 同上五类，逐桶计数 | 多曲线 |
| 插件分布 | `BlockchainRecord` 窗口内按来源插件计数（留痕活跃度） | 环形饼 |
| 组织人员 | 活跃部门人数 / 今日签到人数 / 待处理审批（按审批人部门） | 分组柱状 |

- 「今日在线」以**今日有签到**的员工计（现有系统无在线心跳，注明口径）；
- 无数据 / 图表停用：卡片保留数字，图表位置显示**降级表格 / 数字**，不报错；
- 告警：待我审批 ≥ 3 或插件未全部启用 → 对应图表使用告警色（`--r-danger`，主题内定义）并显示提示。

### 2.4 ChartRenderer 契约扩展（v1.6.2）

`payload(..., kind='cartesian', compact=False, link='', alert=False)`：

| 参数 | 说明 |
|---|---|
| `kind` | `cartesian`（柱 / 线，按 series.type）、`pie`（环形）、`gauge`（进度环） |
| `compact` | 迷你图：隐藏坐标轴与网格留白 |
| `link` | 图表点击跳转 URL（适配器绑定） |
| `alert` | 适配器用主题告警色覆盖首序列颜色 |

- `pie` 的 series 形状：`[{'name': 标签, 'value': 数量}]`；`gauge` 取 `series[0]['value']`（0–100）；
- 主题适配：适配器从 `--r-pink / --r-blue / --r-orange / --r-green / --r-ink` 读取主题色注册 ECharts 主题，两套主题自动换色；告警色取 `--r-danger`（两套主题均已定义）；
- 坐标轴 / 图例 / tooltip 由 Provider 统一生成，业务视图只传数据。

## 三、交互与降级

- hover：tooltip（柱/线 axis 触发，饼/环 item 触发）；
- 点击：环形 → 审批中心；考勤 → 考勤页；流程柱/大盘 → 审批列表；饼 → 留痕链；部门柱 → 组织架构；
- 时间筛选：今日 / 本周 / 本月，链接式联动（保留原页面入口按钮）；
- 响应式：`col-12 col-md-6 col-lg-3`（卡片）、`col-12 col-lg-6`（双栏图表），小屏自动堆叠；图表容器宽度 100%；
- 图表停用：卡片数字与降级表格仍在，页面 200。

## 四、改动面

| 文件 | 动作 |
|---|---|
| `plugin_host/workbench.py` | 新增：范围窗口 / 指标 / 图表 payload 聚合 |
| `plugin_host/views.py` | `index` 接入范围筛选与看板上下文 |
| `plugin_host/charts.py`、`charts/echarts/renderer.py`、`charts/echarts/static/js/echarts.js` | 契约扩展（kind / compact / link / alert + 主题色） |
| `plugin_host/templates/home_dashboard.html` | 新增共享看板模板（两套主题复用） |
| `themes/*/templates/home.html` | 保留 Banner，接线共享看板 |
| `plugin_host/tests_home.py`、`plugin_host/tests_charts.py` | 新增/调整 |
| `locale/en/.../django.po` + `compile_mo.py` | 文案 |
| 文档 | 本文件 + roadmap / README / constraints / development-guide |

无新表、无迁移。

## 五、验收口径

1. 管理员 / 员工视图区块差异符合 §2.2；
2. 三种范围切换后，数字与图表数据同源变化；员工只含本人数据；
3. 图表可点击跳转、hover 有 tooltip；告警条件成立时首序列使用告警色；
4. 图表停用 / 无数据：页面 200，卡片数字与降级表格仍在；
5. 全量测试不回归、`check` / `makemigrations --check` 干净；Docker 重建后两套主题页面正常。

## 六、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| 迁移 | 无新迁移（`makemigrations --check` 干净） |
| 全量单测 | **231 项通过**（v1.6.1 基线 220 + 新增 11：范围 / 角色分流 / 告警 / 降级 / 图表 kind / 大盘数据） |
| 范围联动 | `?range=` 取 `today / week / month`：桶数 24 / 7 / 30；非法值回退 month；数字与图表同源窗口 |
| 角色分流 | 管理员：4 卡 + 大盘 + 插件分布 + 组织人员；员工：个人待办 / 考勤 / 本人发起，无全局与组织图表；无审批权限时隐藏流程区块 |
| 交互 | payload 带 `link`（审批 / 考勤 / 留痕 / 组织架构），适配器绑定点击；tooltip 由 Provider 生成 |
| 告警 | 待办 ≥ 3 或插件未全部启用 → `alert=True` + `--r-danger` 告警色 + 页面徽标 |
| 降级 | 图表停用 / 无数据：卡片数字与降级表格保留，页面 200；无留痕 / 无部门显示空态 |
| 容器验证 | Docker 内以现有管理员 / 员工用户渲染工作台：均 200；管理员含插件分布与大盘，员工不含全局图表 |
| 主题 | 适配器从 `--r-pink / --r-blue / --r-orange / --r-green / --r-ink` 注册 ECharts 主题，两套主题自动换色；告警色 `--r-danger`；`/static/vendor/echarts.min.js` 200 |

