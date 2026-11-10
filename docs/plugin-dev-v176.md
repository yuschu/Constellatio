# 插件开发文档：v1.7.6 列表分页统一 + 公告增量已读 + 留痕翻页

> 关联插件：approval / attendance / user / notice / blockchain + 容器（分页工具与公共模板）
> 版本：v1.7.6 · 文档日期：2026-11-10
> 状态：**✅ 已实现**（387 项测试全绿 + 容器手工验收；见 §六）
> 基线：tag `v1.7.5`（380 项测试）
> 编号说明：v1.7.6 原排「认证后端插件化 + P2 计数原子化」→ 顺延 **v1.7.7**；越权反馈语义统一（302/403/404）随之顺延 **v1.7.8（待定）**。改号已在 roadmap 合并为一句留痕，并改为「版本号在交付时分配」。

## 一、问题复核（实测，动手前逐条核过）

| # | 位置 | 现状 |
|---|---|---|
| A1 | `plugins/approval/views.py:25` | `LIST_PAGE_SIZE = 25`，在 `:121`（我的申请）/`:144`（我的待办）/`:157`（抄送我的）三处 `Paginator(qs, LIST_PAGE_SIZE).get_page(...)` |
| A2 | `plugins/attendance/views.py:307` | 内联 `Paginator(records, 25).get_page(...)`，页大小硬编码在视图里 |
| A3 | `plugins/user/views.py:115`（部门）、`:127`（用户） | 无分页：`Department.objects.all().order_by('id')` / `User.objects...order_by('id')` 全量渲染 |
| A4 | `plugins/notice/views.py:15-28` | 公告列表无分页，一次渲染全部 |
| B | `plugins/notice/views.py:17-22` | **每次进入公告中心**：`values_list('pk')` 取全部公告 id，再对每个 id `bulk_create` 一条 `AnnouncementRead`（`ignore_conflicts=True` 兜重复）。公告越多单次请求写入越大 |
| C | `plugins/blockchain/views.py:119` | 留痕列表硬切 `[:100]`，无分页、无日期筛选；第 100 条以前的记录 UI 上不可达（审计看不全） |
| **A5** | `approval_list.html:64`、`approval_cc.html:43`、`approval_pending.html:47` | **真实缺陷**：翻页链接是裸 `?page=N`，会整体覆盖 query string。审批列表一旦带上任何筛选/携带参数，点「下一页」就丢参数回到全量列表（`attendance` 旧实现是手工枚举参数，虽能带住但每加一个参数就要改一次，且已漏掉 `month`） |

现有分页模板块共 4 处重复（`approval_list.html:57`、`approval_pending.html:40`、`approval_cc.html:36`、`attendance_records.html:183`），各写一套「第 X / Y 页 + 上一页 / 下一页」，且链接是裸 `?page=N`（会把 `status` / `type` / `from` / `to` 等筛选参数丢掉）。

容器实测数据（作为验收基准）：`blockchain_record = 693`、`notice_announcement = 6`、`notice_announcementread = 94`、`department = 20`、`user = 32`。

## 二、框架事实（现读 Django 5.2.18，不靠记忆）

1. **`Paginator.get_page()` 语义**（`django/core/paginator.py`）：非整数 → 第 1 页；`EmptyPage`（越界）→ **末页**；其余走 `validate_number`。所以「越界页回落末页」不需要自己写判断。
2. **`{% querystring %}` 是 Django 原生标签**（`django/template/defaulttags.py`，`takes_context=True`）：默认取 `context.request.GET`，支持 `{% querystring page=3 %}` 改单值、`{% querystring foo=None %}` 删参数，返回值自带 `?`。
   → **不需要自定义模板标签，也不需要手工拼接 `request.GET.urlencode`**。这是本版保住筛选参数的正解。
3. `Page` 暴露 `count` / `has_next` / `has_previous` / `next_page_number` / `previous_page_number` / `paginator.num_pages` / `paginator.count`，公共模板只用这些。

## 三、设计口径（契约）

| 项 | 决策 |
|---|---|
| 页大小 | `DEFAULT_PAGE_SIZE = 25`（approval / attendance / user / notice 沿用现有 25）；**留痕 50**（审计场景一行表格更密，693 条 → 14 页） |
| 唯一分页入口 | `plugin_host/pagination.py` 的 `paginate(request, queryset, page_size=DEFAULT_PAGE_SIZE)` → `Paginator(qs, size).get_page(request.GET.get('page'))`；视图里不再出现 `Paginator(` 字面量 |
| `approval.LIST_PAGE_SIZE` | 改为 `LIST_PAGE_SIZE = DEFAULT_PAGE_SIZE` 引用，保留名字（模板/用例未引用它，但避免下一个人再定义一份数字） |
| 排序 | **分页之前定死顺序**：user 已有 `order_by('id')`；notice 显式 `order_by('-is_top', '-created_at')`（与 `Meta.ordering` 一致但要写出来，避免 MySQL 在无 ORDER BY 的 LIMIT 下抖动）；blockchain 显式 `order_by('-id')`；approval / attendance 已有筛选+排序，不改 |
| 公共模板 | 新建 `templates/includes/pagination.html`（项目根 `templates/` 已在 `DIRS` 且由 `filesystem.Loader` 命中，两套主题都能 include）；4 处既有分页块全部替换为 `{% include 'includes/pagination.html' %}`，链接用 `{% querystring page=... %}` |
| 公告增量已读 | 顺序固定：① 取当页 `announcements`（分页后的 `page_obj`）② `AnnouncementRead.objects.filter(user=request.user, announcement__in=page_obj).values_list('announcement_id', flat=True)` 得已读集合 ③ 差集 `bulk_create(..., ignore_conflicts=True)`。**保留 `ignore_conflicts=True`** 作并发兜底（两请求同时登记时靠唯一键去重） |
| 留痕 | `paginate(request, BlockchainRecord.objects.select_related('operator').order_by('-id'), 50)`；模板显示 `page_obj.paginator.count`（总数 693）；**看板走 60 秒快照 `_stats_snapshot()`**（键 `blockchain:stats:{days}:{localdate}`，与 `_verify_snapshot` 同套路）。**不能用「只在第 1 页算」**：直接打开 `?page=2`（书签 / 刷新 / 别人发的链接）第 1 页从没渲染过，看板会是空的。代价是每请求多 1 次 `cache.get`（DatabaseCache 一次 SELECT），省掉 2 次聚合查询 |
| 参数保留 | 审批/考勤的 `status` / `type` / `from` / `to` 等筛选参数一律经 `{% querystring %}` 透传；`page` 之外的参数不改 |
| 禁止 | 不一次改 5 个列表各写一套模板（只写一个 include）；不加前端 JS 排序；不改页大小语义 |

## 四、实现清单（逐文件、逐函数；确认后按此顺序小步改）

1. **`plugin_host/pagination.py`（新）**：`DEFAULT_PAGE_SIZE = 25` + `paginate()`，docstring 写清 `get_page` 的越界/非法语义与「必须先排序再分页」的约定。
2. **`templates/includes/pagination.html`（新）**：`{% if page_obj.paginator.num_pages > 1 %}` 才渲染；上一页/下一页用 `{% querystring page=... %}`；中间 `<span>` 显示「第 X / Y 页」。只读 `page_obj`，不引入任何 JS。
3. **`plugins/approval/views.py`**：`:25` 改引用 `DEFAULT_PAGE_SIZE`；`:121/:144/:157` 三处改调 `paginate(request, ...)`；删掉本地 `Paginator` 导入（若不再使用）。
4. **`plugins/attendance/views.py`**：`:307` 改调 `paginate(request, records)`。
5. **`plugins/user/views.py`**：`department_list` / `user_list` 接 `paginate`，模板改循环 `page_obj` 并 include 分页块。
6. **`plugins/notice/views.py`**：`notice_list` 改「分页 → 当页已读集合 → 差集登记」；模板循环 `page_obj` + include 分页块。
7. **`plugins/blockchain/views.py`**：`blockchain_list` 改 50/页 + `total` + 第 1 页才算 `_window_stats`；模板加总数与分页块。
8. **4 个既有模板**：把各自的分页块替换为 `{% include 'includes/pagination.html' %}`（`approval_list` / `approval_pending` / `approval_cc` / `attendance_records`）。
9. **文档同步**：本文件定稿 + `docs/roadmap.md`（v1.7.6 行、顺延 v1.7.7 / v1.7.8）+ README 状态行 + `constraints-and-acceptance.md` 进度行。

## 五、测试记录（实际 7 条，380 → 387）

`plugin_host/tests_pagination.py`：

| # | 用例 | 断言要点 |
|---|---|---|
| 1 | `test_page_size_applies` | 60 条留痕 → 首页 `paginator.count=60`、本页 50 行、`num_pages=2`、只渲染 50 条详情链接、页面显示「共 60 条」 |
| 2 | `test_out_of_range_page_falls_back_to_last` | `?page=999` → `page_obj.number == num_pages`，末页 10 行 |
| 3 | `test_pagination_reaches_old_records` | 最旧一条首页不可见、第 2 页可见（原来 `[:100]` 永远看不到） |
| 4 | `test_pager_keeps_filter_params` | 签到详情 `?status=late` → 下一页链接含 `status=late` 与 `page=2`；第 2 页的上一页链接为 `?status=late`（**不带 `page=1`**） |
| 5 | `test_only_current_page_is_registered` | 30 条公告 → 首次只登记当页 25 条（集合相等校验），第 2 页补齐剩 5 条 |
| 6 | `test_second_visit_inserts_nothing` | 二次进入公告中心：通知表 INSERT 语句 **0 条**（首次 1 条 bulk） |
| 7 | `test_user_list_paginates` | 31 个用户 → 首页 25、第 2 页 6，`paginator.count=31` |

> 注意 sqlite 下 `bulk_create(ignore_conflicts=True)` 生成的是 **`INSERT OR IGNORE`**，断言「有没有插入」要匹配 `INSERT` + 表名，写死 `INSERT INTO` 会永远数到 0（第一版用例就是这么写的，已修）。

## 六、验收记录（2026-11-10 实测）

容器（MySQL + 3 worker + 真实演示数据）跑手工冒烟，本地跑全量用例。

### 6.1 留痕：693 条 / 50 一页 / 第 14 页有数据

```
page1: status=200 | 本页行数=50 | 总数显示=693 | 分页块=['?page=2'] | 页码「第 1 / 14 页」
page14: status=200 | 行数=43   （693 = 13×50 + 43）
```

### 6.2 公告中心：首次 1 条 bulk INSERT、二次 0 条

测试库实测（30 条公告、页大小 25，`CaptureQueriesContext` 统计）：

```
公告总数 = 30 | 页大小 = 25
首次访问：通知表 INSERT 语句 1 条 → 已读行数 25
再次访问：通知表 INSERT 语句 0 条 → 已读行数 25（0 新增）
第 2 页 ：通知表 INSERT 语句 1 条 → 已读行数 30（补齐余下 5 条）
首次 INSERT 形态：INSERT OR IGNORE INTO "notice_announcementread" (...) VALUES (...)
```

> 整页 SQL 总数（首次 89 / 再次 85）主要被菜单、未读数等上下文处理器占掉，不是公告登记本身；
> 因此断言只钉「通知表的 INSERT 条数」，不钉总查询数（避免脆断言）。

### 6.3 翻页保住筛选参数（修复 A5 的直接证据）

签到详情（容器数据在 2026-09，故显式给 `start`/`end`）：

```
page1: ?status=late&start=2026-09-01T00:00&end=2026-09-30T23:59
       分页链接 = ?status=late&start=...&end=...&page=2      ← 参数全在
page2: 分页链接 = ?status=late&start=...&end=...             ← 上一页：省掉 page 参数
                ?status=late&start=...&end=...&page=3        ← 下一页：继续带着参数
```

审批列表：容器里每个申请人的审批都 < 1 页（最大 2 条），分页块不渲染，**无法用容器数据演示**；
该机制由 §五 第 4 条用例覆盖（同一 include，与列表类型无关）。另核实：审批列表当前**没有**
`status` 之类的筛选参数（只有行内 POST 表单），所以 A5 在审批上的表现是「一旦将来加筛选就会丢」，
在签到详情上是「手工枚举参数、漏一个就丢」（它的旧实现已漏掉 `month`）。

### 6.4 门禁与用例

- `manage.py check` 无问题 / `ruff check .` All checks passed / **Ran 387 tests OK**（380 + 7）。
- 受影响插件回归：`plugins.approval plugins.attendance plugins.user plugins.notice plugins.blockchain` 共 167 项全绿。

### 6.5 实现期踩的两个坑（都已在代码/用例里固化）

1. **模板块替换不能按「第一个 `{% endif %}`」截断**：旧分页块里还有内层 `{% if page_obj.has_previous %}`，用非贪婪正则替换会截在内层 `endif`，留下孤立的 `{% endif %}`，模板直接 `TemplateSyntaxError: Invalid block tag ... expected 'endblock'`（4 个模板全中）。改成按 `{% if %}` / `{% endif %}` 配平后再整块替换。
2. **`read_count` 是标注在分页查询里算出来的**：登记已读发生在查列表**之后**，所以本页的「已读 N 人」不含刚插入的这一条；不重查、原地 `+= 1` 补上（省一次聚合，也保持「当次访问就把自己算进去」的语义）。

## 七、不做 / 已知边界

- 不把 5 个列表各写一套分页模板（只有一个 `includes/pagination.html`）；不加前端 JS 排序/筛选。
- 不改 `DEBUG`、不改页大小语义、不给分页加缓存。
- **留痕的日期/来源筛选不在本版**：C 只要求「按页取 + 保留总数」，审计时段筛选列待办。

## 八、待办观察（本版不修）

1. **留痕缺日期/来源筛选**：693 条能翻完，但「只看某天 / 某插件」仍做不到；与「按日 × 来源统计看板」口径可复用，列入后续。
2. **未纳入本版的列表**：`notice_readers`（已读人员明细）、`notify` 消息中心（硬切 `[:200]`）、`structure` 责任人清单——本版只按负责人点名的 5 个列表改，其余留待统一。
3. **公告已读登记的并发面**：两个请求同时判定「未读」时各自 insert，靠 `unique_together` + `ignore_conflicts=True` 去重；不会产生重复行，但会多一次无副作用写入。
4. **页大小口径分散**：approval/attendance/user/notice 25、blockchain 50。若将来要按用户偏好配置，需要进设置页（不属本版）。
