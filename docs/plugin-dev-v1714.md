# 插件开发文档：v1.7.14 三处重业务逻辑下沉 services

> 关联：`plugins/user/services.py`（新）、`plugins/attendance/services.py`（新）、`plugins/approval/services.py`（追加）
> 版本：v1.7.14 · 文档日期：2026-11-12
> 状态：**✅ 已实现**（467 项测试；见 §四）
> 基线：tag `v1.7.13`（440 项测试）
> 范围：只动 user / attendance / approval 三个插件；其余 4 个插件不碰

## 一、改了什么（只三处）

| # | 原位置 | 新位置 | 内容 |
|---|---|---|---|
| 1 | `plugins/user/views.py::user_status` | `plugins/user/services.py` | 状态机（启用/禁用/冻结/解冻）+ 超管 L0 保护 + 普通管理员「先冻结再发起会签」分支 |
| 2 | `plugins/attendance/views.py::attendance_check`、`::attendance_makeup`，以及 `models.Attendance.compute_status` | `plugins/attendance/services.py` | 状态判定（纯函数，传 `rule` 时零查询）、打卡（锁内重读 + 只写改动字段）、补卡登记 |
| 3 | `plugins/approval/views.py::approval_attachment` + 建单里的附件赋值、`views._may_view`、`forms` 的附件校验常量 | `plugins/approval/services.py`（追加） | 附件校验（扩展名/大小）、落盘、下载鉴权、对象可见性判定 |

## 二、判据：什么放 views、什么放 services（新增插件照抄这一节）

**放 services 的**（满足任一条即放）：

1. **有业务规则**：状态机、权限阶梯、阈值判定、金额/附件校验这类「换个界面也要一样」的判断。
2. **要能脱离 HTTP 验证**：需要 `manage.py shell` 或单测直接用**显式参数**调用（当前用户显式传，
   不读 `request`）。
3. **可能被第二条路径复用**：管理命令、审批回调、信号订阅、后台任务。
4. **需要事务/行锁**：`transaction.atomic()` 与 `select_for_update()` 的边界属于业务语义，
   写在 service 里才不会被某个视图漏掉。

**放 views 的**：

1. **参数提取**：`request.POST.get(...)`、`get_object_or_404`、解析表单/日期字符串。
2. **HTTP 语义**：`redirect` / `render` / 状态码 / `require_perm` / `login_required` 装饰器。
3. **消息与 i18n**：用户可见文案（`_('...')`）。
4. **把 service 的结果翻译成响应**（例：`attachment_for` 返回 `None` → 回详情页）。

**service 的签名约定**：

```python
def change_status(operator, target, action) -> str: ...      # 返回语义名，不返回 HttpResponse
def check(user, *, action, sign_type=None, now=None): ...     # now 注入为了可测
def judge_status(*, is_makeup, check_in, check_out, rule=None): ...  # 纯函数，rule 传入即零查询
def attachment_for(user, approval): ...                       # 无权抛 ObjectPermissionDenied
```

**红线**：

- service **不读 `request`**、不返回 `HttpResponse`、不做重定向；
- service **不 import 其他插件的 models**（跨插件只能通过 `django.apps.apps.get_model` 在视图层取，
  或走信号）；本次 `attendance_makeup` 的「取目标用户」仍留在视图里就是这条规则的体现；
- 锁与事务**原样搬家**，不得因为搬家降级为无锁（本次两条写路径都保留了
  `atomic()` + `select_for_update()`，`save(update_fields=...)` 的字段集一字未改）。

## 三、视图行数对比（非空行，`git show HEAD:` 对比）

| 视图 | 改前 | 改后 |
|---|---|---|
| `user.views.user_status` | **48** | **13** |
| `attendance.views.attendance_check` | **37** | **17** |
| `attendance.views.attendance_makeup` | **25** | **15** |
| `approval.views.approval_attachment` | 13 | 12 |

四个视图都 ≤ 30 行，且只做「取参数 → 调 service → 响应」。

### 3.1 关于「每请求查开关表」的数字（v1.7.13 的遗留校正）

外部 review 用 `CaptureQueriesContext` 真发请求测了（`venv/v1714_evidence_switch_queries.py`）：

| 页面 | 查 `workspace_pluginswitch` |
|---|---|
| 首页 `/` | **6** |
| `/plugins/blockchain/`（有图表） | **4** |
| `/plugins/attendance/records/`（有图表） | **4** |
| `/plugins/structure/`（无图表） | **3** |
| `/plugins/notice/`（无图表） | **3** |

所以准确口径是**带条件的区间**：**首页 6 次；插件页 3~4 次**（有图表的多一次，因为
`charts.chart_switch_enabled` 会经 `get_active_chart` 再查）。之前 v1.7.13 文档写的
「普通页 4 次」偏高 1，「1~2 次 / 首页 3~4 次」偏低——**两处都是数调用点、没跑请求**。

## 四、验收记录（2026-11-12）

### 4.1 门禁

`check` / `ruff` / `makemigrations --check` 通过；全量 **467 项**（440 + 27）。

### 4.2 既有断言一条未改（本版范围内）

user / attendance / approval 三个插件的既有用例**零改动**（`git diff HEAD -- plugins/*/tests*.py` 里只有
新增的 `tests_services.py`）。搬家时保留了既有测试依赖的接缝：

- `attendance.views._now()` 仍由视图调用并**注入** `services.check(..., now=_now())`——
  否则 `mock.patch('plugins.attendance.views._now')` 那组用例会全红（实测踩到过，见 §4.4）。

### 4.3 新增 service 单测 26 条

| 文件 | 条数 | 覆盖 |
|---|---|---|
| `plugins/user/tests_services.py` | 6 | 超管直接禁用 / 普通管理员走会签 / 冻结解冻幂等 / 启用清冻结 / 非超管操作超管抛 `StatusChangeDenied` / 未知动作抛 `ValueError` |
| `plugins/attendance/tests_services.py` | 11 | 补卡优先 / 缺卡 / 迟到 / 早退 / 正常 / **纯函数零查询**（`assertNumQueries(0)`）/ 重复打卡只一行 / 签退不清签到 / 补卡状态与类型 / 补卡幂等 / 阈值含宽限 / 模型 save 走 service 口径 |
| `plugins/approval/tests_services.py` | 9 | 扩展名白名单 / **超限**（mock 放大 size）/ 落盘 / 非法不落盘 / 可见性矩阵 / 无权限下载抛 `ObjectPermissionDenied` / 无附件返回 None / 相关人可取句柄 |
| 合计 | **27** | 6 + 12 + 9（440 + 27 = 467；attendance 多一条 operator 日志用例） |

### 4.4 实现期发现的两个测试时间依赖（已修，非放宽断言）

1. `plugin_host/tests_pagination.QueryParamPreservationTests` 用 `check_in=timezone.now() - timedelta(days=day)`
   造 30 条记录，再按 `status=late` 翻页。而状态判定是「`check_in` 晚于迟到阈值 → LATE，否则看 `check_out`；
   没有 `check_out` → MISSING」。**早上 8:45 跑必红**（打卡时间在阈值前 → 全部 MISSING），晚上跑就绿。
   修法：把打卡时间固定为当天 09:30，与运行时刻脱钩。
2. 上面这条与 v1.7.9 收尾修的 `attendance.tests.AttendanceRecordFilterTests` 是同一类问题，
   当时只扫了 attendance 自己的用例，漏了 plugin_host 里的分页用例。

### 4.5 锁与事务边界核对

| 路径 | 搬前 | 搬后 |
|---|---|---|
| 打卡 | `atomic()` 包 `get_or_create` → `select_for_update().get()` → 仅写 `changed + ['status','updated_at']` | 同左，逐行搬入 `services.check` |
| 补卡 | `atomic()` 包 `get_or_create` → `select_for_update().get()` → 写 6 个字段 | 同左，搬入 `services.register_makeup` |
| 建单附件 | 事务内 `Approval.objects.create(attachment=...)` | 事务内 create 后调 `services.store_attachment`（校验 → 赋值 → save） |
| 审批状态机 | 未改 | 未改 |

### 4.6 行为变更：未知状态操作从「静默重定向」变为 500

原 `user_status` 是 if/elif 链且没有 else：`POST status=xxx` 会**静默** redirect 回列表页。
重构后 `services.change_status` 末尾 `raise ValueError(...)`，异常穿过视图由
`ExceptionGuardMiddleware` 处理 → **HTTP 500**。

- 方向：不静默吞异常（外部 review 赞成）；
- 影响面：正常 UI 只发 `enable` / `disable` / `freeze` / `unfreeze` 四个值，实际碰不到；
  但这是**用户可见的行为变化**，写在这里备查（v1.7.7 的 `LOGIN_FAIL_LIMIT` 语义变化同样单列过）；
- 若将来希望它变成 400，正确做法是把 ValueError 换成 `BusinessError`（v1.7.5 的 400 通道），
  而不是把这个分支再改回静默。

### 4.7 `register_makeup(operator, ...)` 的参数不是装饰

`AuditModel` 的 `created_by/updated_by` 记录的是「这一行被哪个请求写过」，**不等于**「谁发起这次补卡」。
所以 `operator` 用于一条留痕日志：

```python
logger.info('补卡登记 operator=%s target=%s date=%s status=%s', ...)
```

shell 调用时 `operator` 可为 None（那正是「无请求上下文」的场景，日志里记成 None 是准确的）。
有用例 `test_register_makeup_logs_operator` 钉住它——防止将来又被当成死参数删掉或重新变成无用。

## 五、不做 / 已知边界

- 不动 auth / notice / notify / blockchain / structure / workspace / sso / theme 等其余插件。
- 不把 `require_perm` 之类的 HTTP 装饰器下沉到 service（它们依赖 `request`，属于视图层）。
- `attendance` 的 `_combine` / `parse_date` 等解析工具仍在视图层（属参数提取），没有搬进 service。
- `approval._can_act`（审批动作权限）仍在视图层：它决定「当前这个请求能不能点通过按钮」，
  与服务的流转校验（`services.approve` 内的 `PermissionError`）互为双保险，本次不合并。

## 六、给下一次的提醒

1. `save(update_fields=[...])` 的字段集是业务语义的一部分（v1.7.8 的审计列曾因漏写而静默失效）。
   搬家时必须连同字段集一起搬，并核对既有测试里对状态/时间的断言。
2. 测试里用 `timezone.now()` 造数据 + 按状态/时间筛选，几乎一定会随运行时刻变色；
   要用固定的业务时刻（如 09:30），或显式传 `start`/`end`。
