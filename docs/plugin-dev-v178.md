# 插件开发文档：v1.7.8 审计字段统一（AuditModel + 当前用户上下文）

> 关联：容器（`plugin_host/models.py` / `current_user.py` / `audit.py` / `middleware.py` / `apps.py`）、插件 notify / blockchain / workspace / approval / attendance / notice / user
> 版本：v1.7.8 · 文档日期：2026-11-10（由 v1.7.7 草案改号而来，原文未动逻辑，按 §八 的 5 条裁定修）
> 状态：**草案 —— 等 v1.7.7 交付后再逐条过**
> 基线：tag `v1.7.6`（387 项测试全绿）
> 覆盖：**13 / 14 个插件模型**（全部纳入 user 三模型；`structure.StructureRecord` 明确排除，理由见 §六 第 1 条）

## 一、问题复核（实测盘点）

用 `apps.get_models()` 扫全部插件模型（脚本：`venv/v177_evidence/audit_field_inventory.py`）：

**实测：插件模型 14 个，`created_at` 9 个，`updated_at` 8 个。** 清单如下（要核对差异，就看这张表，不做推测式归因）：

| 模型 | db_table | 现有审计字段 |
|---|---|---|
| approval.Approval | approval_approval | created_at, updated_at |
| approval.ApprovalRecord | approval_approvalrecord | created_at, operator |
| approval.ApprovalSigner | approval_approvalsigner | signed_at |
| attendance.Attendance | attendance_attendance | created_at, updated_at |
| attendance.AttendanceRule | attendance_attendancerule | updated_at, updated_by |
| blockchain.BlockchainRecord | blockchain_record | created_at, operator |
| notice.Announcement | notice_announcement | created_at, updated_at |
| notice.AnnouncementRead | notice_announcementread | read_at |
| notify.Notification | notify_notification | created_at, read_at |
| structure.StructureRecord | structure_structurerecord | applied_at, applied_by |
| user.Department | user_department | created_at, updated_at |
| user.Role | user_role | created_at, updated_at |
| user.User | user_user | created_at, updated_at |
| workspace.PluginSwitch | workspace_pluginswitch | updated_at, updated_by |

- 缺 `created_at` 的 5 个：ApprovalSigner、AnnouncementRead、AttendanceRule、PluginSwitch、StructureRecord（后者用 `applied_at`）。
- 缺 `updated_at` 的 6 个：ApprovalRecord、ApprovalSigner、BlockchainRecord、AnnouncementRead、Notification、StructureRecord。

操作人字段手写处（逐条核实）：

| 位置 | 写法 |
|---|---|
| `plugins/workspace/views.py:51` | `PluginSwitch.objects.update_or_create(..., defaults={'enabled':…, 'updated_by': request.user})` |
| `plugins/attendance/views.py:135` | `rule.updated_by = request.user`（`form.save(commit=False)` 后手填） |
| `plugins/approval/services.py:32` / `views.py:259` | `ApprovalRecord.objects.create(..., operator=request.user / operator=operator)` |
| `plugins/blockchain/models.py:71-90` | `BlockchainRecord.append(..., operator=None)`，由调用方传 |

## 二、设计口径（契约）

### 2.1 `plugin_host/models.py`：抽象基类

```python
class AuditModel(models.Model):
    """审计字段基类（v1.7.8）：写入经 pre_save 自动填操作人。"""
    created_at = models.DateTimeField('创建时间', auto_now_add=True, null=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+',
                                   verbose_name='写入用户')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+',
                                   verbose_name='最后修改人')

    class Meta:
        abstract = True
```

- `related_name='+'`：不给用户模型加反向管理器。已 grep 全仓：**没有任何代码依赖** `pluginswitch_set` / `attendancerule_set` 反向名（只有模型定义与直查），统一成 `'+'` 安全。
- `created_by` 的 verbose_name 用**「写入用户」**而不是「操作人」，是为了和既有 `operator`（被留痕的那个操作由谁发起）在界面上区分开。

### 2.2 `plugin_host/current_user.py`

照 `theming.py` 的 token 写法：

```python
_CURRENT_USER = contextvars.ContextVar('current_user', default=None)

def set_current_user(user):      return _CURRENT_USER.set(user)
def reset_current_user(token):   _CURRENT_USER.reset(token)
def get_current_user():          return _CURRENT_USER.get()      # 无上下文 → None
```

边界与 `request_id.py` 一致：`process_response` / `response_for_exception` 之后读 contextvar 一律为空。审计填充发生在 `pre_save`（写库期间），所以安全；**不要在响应阶段或信号回调里依赖它**。

### 2.3 中间件：入口 set、`finally` reset、**匿名映射成 None**

`CurrentUserMiddleware`（`plugin_host/middleware.py`），放在 **`LoginRequiredMiddleware` 之后、`MessageMiddleware` 之前**（此时 `request.user` 已可用）：

```python
def _current_user(request):
    user = getattr(request, 'user', None)
    # 关键：AnonymousUser 必须映射成 None。直接把 request.user 塞进 FK 会在保存时抛
    # ValueError: Cannot assign "AnonymousUser": "X.created_by" must be a "User" instance
    return user if user is not None and user.is_authenticated else None


def __call__(self, request):
    token = set_current_user(_current_user(request))
    try:
        return self.get_response(request)
    finally:
        reset_current_user(token)      # 异常 / 重定向 / 500 路径都复位，杜绝串号
```

### 2.4 `pre_save` 信号：统一填 `created_by` / `updated_by`

在 `plugin_host/apps.py:ready()` 里连接（`dispatch_uid='plugin_host.audit.fill_operator'`，避免 autoreload 重复连接）；**只对 `issubclass(sender, AuditModel)` 生效**，其余模型早退。

| 场景 | 行为 |
|---|---|
| 新建（`instance._state.adding`）且 `created_by_id is None` | 填 `created_by = 当前用户或 None`，同时填 `updated_by` |
| 更新 | 只在有当前用户时填 `updated_by`；**不覆盖已有值**（后台任务不会把线上记录的操作人清空） |
| 上下文为空（`manage.py shell` / 后台线程 / 信号内写入） | 新建时 `created_by = None`，**不报错**；更新时不动原值 |
| 显式传了 `created_by` | 尊重调用方，不覆盖 |

### 2.5 与既有字段：三处必须说清

1. **`operator` 保留，不与 `created_by` 合并**：`operator` 是「被留痕操作的业务主体」，`created_by` 是「写入这条审计行的请求用户」，信号写入时两者可能不同（例如公告发布信号里写留痕，触发者是发布人，但写入主体是订阅方）。字段名一律不动。
2. **`AttendanceRule.updated_by` / `PluginSwitch.updated_by` 改为继承基类**：本地声明删掉。两处现有定义与基类有**纯 ORM 层差异**（`related_name`：`'+'` vs 默认；`verbose_name`：`最后修改人` vs `最后操作人`），统一进基类后 `makemigrations` 会生成 **`AlterField`**——`related_name` / `verbose_name` **不产生任何 `ALTER TABLE`**。
   **合格判据（不是「没有 AlterField」）**：`sqlmigrate <app> <迁移号>` **输出为空**，且 `migrate` 前后 `SHOW CREATE TABLE` 完全一致。不为了消掉 `AlterField` 去扭曲模型定义。
3. 视图里 `rule.updated_by = request.user` / `defaults={'updated_by': …}` 这类手动赋值**保留不动**：与 pre_save 的「显式传入不覆盖」规则一致，不会打架。

### 2.6 迁移：两批，全部 nullable，无数据迁移

| 批次 | 应用 | 内容 |
|---|---|---|
| 第一批 | notify / blockchain / workspace | 各下一个编号迁移：新增 `created_by` / `updated_by` / 缺失的 `updated_at` 或 `created_at`；workspace / attendance 的 `updated_by` 走 `AlterField`（空 SQL） |
| 第二批 | approval / attendance / notice | 同批逻辑，各模型补齐 4 个审计字段（已有 `created_at` 的模型只加 `created_by` / `updated_by`） |
| 第三批（本轮新增） | **user** | Department / Role / User 已有 `created_at` / `updated_at`，只加 `created_by` / `updated_by` |
| 不动 | structure | 明确不纳入（§六 第 1 条） |

- **历史行 `created_at` 为 NULL**：`auto_now_add=True, null=True` 只对新行生效。5 个模型（ApprovalSigner、AnnouncementRead、AttendanceRule、PluginSwitch、user 之外无）迁移后既有数据 `created_at` 永远是 NULL（容器里就有 94 条 `AnnouncementRead`）。**不用 `RunPython` 回填迁移执行时间**——那是伪造审计时间。文档与验收都写明「v1.7.8 之前的历史行无创建时间」。
- 可回滚：`migrate <app> <上一个迁移>` 会 `RemoveField` 掉新增列（`AlterField` 回滚为空操作），逐应用实测往返。

## 三、写入路径 → 是否留审计（本版的关键边界表）

`pre_save` 只在 `Model.save()`（及 `create()` / `update_or_create` 的保存分支）触发；以下路径**不会**填审计人，本版不改造它们：

| 写入路径 | 位置 | 走 pre_save？ | 结果 |
|---|---|---|---|
| 公告流量的批量已读登记 | `plugins/notice/views.py`（`bulk_create(ignore_conflicts=True)`，v1.7.6） | ❌ `bulk_create` 不发信号 | `created_by` 为 NULL |
| 站内信批量发送 | `plugins/notify/apps.py:32`（`Notification.objects.bulk_create`） | ❌ | 同上 |
| 标记已读 | `plugins/notify/views.py:35,49`（`QuerySet.update()`） | ❌ `update()` 不发信号 | `updated_by` 保持原值 |
| 插件开关命令 | `manage.py plugin_switch`（`update_or_create`） | ✅ 但无请求上下文 | `updated_by` 保持原值 / 新建为 NULL |
| 信号内写入（留痕、站内信） | `blockchain` / `notify` 的 `post_save` 回调 | ✅ 有上下文时填 | 后台触发时为 NULL |
| 注册表统计直读 | `plugin_host/registry.py`（`values_list`） | — 只读 | 不涉及 |

**理由**：批量路径改成逐条 `save()` 有性能代价；`update()` 本身无法得知「谁改的」。要补需要在服务层显式传 `updated_by=...`，属于后续项（§七）。

## 四、实现清单（逐文件；v1.7.7 交付后按此顺序做）

1. `plugin_host/models.py`（新）：`AuditModel`。
2. `plugin_host/current_user.py`（新）：contextvar 三件套。
3. `plugin_host/audit.py`（新）：`pre_save` receiver + `connect_audit_signals()`。
4. `plugin_host/apps.py`：`ready()` 调 `connect_audit_signals()`。
5. `plugin_host/middleware.py`：`CurrentUserMiddleware`（匿名 → None）；`settings.MIDDLEWARE` 插到 `LoginRequiredMiddleware` 之后。
6. 第一批模型 + 迁移：notify / blockchain / workspace。
7. 第二批模型 + 迁移：approval / attendance / notice。
8. 第三批模型 + 迁移：user。
9. `docs/database-design.md`：审计字段口径统一（哪些表有、语义、NULL 含义、structure 差异原因）。
10. 测试 `plugin_host/tests_audit.py`（见 §五）。
11. 文档：本文件定稿 + roadmap / README / constraints 同步。

## 五、测试计划（新增 7 条）

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_http_create_sets_created_by` | HTTP 新建公告 → `created_by == 当前用户`、`updated_by == 当前用户` |
| 2 | `test_http_update_sets_updated_by_keeps_created_by` | 换用户 HTTP 编辑 → `updated_by` 变新用户、`created_by` 不变 |
| 3 | `test_no_request_context_gives_null` | 无中间件 `Announcement.objects.create(...)` → 两字段 None，**不抛异常** |
| 4 | `test_context_reset_on_exception` | A 建一条 → 触发一次 500（夹具 `/boom/`）→ A 再建：仍是 A；换 B 建 → 是 B |
| 5 | `test_explicit_created_by_not_overwritten` | A 上下文里 `create(..., created_by=B)` → 仍是 B |
| 6 | `test_anonymous_request_does_not_crash` | 匿名请求触发的写入（登录页相关路径）不因 `AnonymousUser` 抛 ValueError |
| 7 | `test_structure_excluded_from_audit` | `StructureRecord` **没有** `created_at`/`created_by` 列（`_meta` 断言），只有 `applied_at`/`applied_by`——防止后人再用 property 别名伪装 |

手工验收（不进套件）：
- 每个应用 `migrate <app> <上一个>` → 前滚往返；
- `sqlmigrate` 对 `AlterField` 迁移输出为空；`SHOW CREATE TABLE` 前后一致；
- 既有行（容器 94 条 AnnouncementRead）迁移后 `created_at IS NULL` 且页面不报错。

## 六、不做 / 已知边界

1. **`structure.StructureRecord` 明确排除**：它只有 `applied_at` / `applied_by`，没有 `created_at` / `created_by` / `updated_by` 列。
   - **否决「加 property 别名」方案**：别名会让界面/文档显示「这个模型有审计字段」，实际不落库、不填值、不可查——把未实现伪装成已实现，比不做更糟。
   - 若要给它审计人，只能**真加两列**（`created_by` / `updated_by`，nullable + `SET_NULL`，多一次迁移）。本版不做：它已有 `applied_at` + 状态流转，审计价值低。
2. 不改既有字段名（`applied_at` / `operator` / `updated_by` 一律保留）；不删 `operator`；不做数据回填。
3. 批量路径不填审计人（见 §三表），本版不改造。
4. **历史行 `created_at` 为 NULL**（§2.6）。

## 七、待办观察

1. 批量写入（`bulk_create` / `update()`）的审计填充：需要服务层显式传参，或改逐条 `save()`（有性能代价）。
2. 历史行 `created_by IS NULL` 的展示口径（管理页显示「历史数据」而不是空白）。
3. `structure` 是否真加 `created_by` / `updated_by` 两列（若它的变更单需要追责）。
4. 审计字段是否要进管理页列表/筛选（当前只有列，没有 UI）。

## 八、本版按裁定修改的 5 处（留档）

| # | 裁定 | 落地 |
|---|---|---|
| 1 | 不写「15/10/9 + 可能是把谁算进去了」的推测 | §一 只留实测 14/9/8 + 模型清单；不做归因推测 |
| 2 | 覆盖 13/14 与标题一致 | 纳入 `user` 三模型（第三批迁移）；`structure` 明确排除并写原因 |
| 3 | structure 别名方案否决 | 删除 property 别名；§六 第 1 条给出「明确排除」与「真加两列」两个选项，选前者 |
| 4 | 匿名必须映射 None | §2.3 写死 `_current_user()`，并配 `test_anonymous_request_does_not_crash` |
| 5 | `AlterField` 不是判据 | §2.5/§2.6 改为「`sqlmigrate` 空 SQL + `SHOW CREATE TABLE` 前后一致」；不再要求「改成一致再继续」 |
