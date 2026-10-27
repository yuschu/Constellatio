# 插件开发文档：v1.7.1 安全与并发修复包

> 关联插件：plugin_host（注册表 / 系统检查 / 开关缓存 / 工作台）、approval（状态机 / 鉴权 / 列表）、blockchain（链写入 / 校验 / 信号）、attendance（打卡）、workspace（开关）、user（用户状态 / 密码）、auth（登录）、sso、notify
> 版本：v1.7.1 · 文档日期：2026-10-27
> 状态：**✅ 已实现**（323 项测试全绿 + Docker 重建 + 容器内 9 页冒烟）
> 定位：原 `roadmap.md` 第四节「v1.10 修复包」中可提前的部分，**提前到 v1.7.1 落地**；认证后端插件化顺延至 v1.7.2

## 一、需求

起因是 2026-10-27 的一次只读代码质量评估（四路分工：安全与配置、容器核心、业务插件、测试与工程化）。评估结论按严重度分为 P0-A（部署默认值）、P0-B（并发写入）、P0-C（授权边界）、P1（性能与工程化）。本版只做 **P0-B + P0-C + 全部 P1**，共 21 项：

| 组 | 条目 | 本版 |
|---|---|---|
| P0-B | 审批状态机无事务无锁、留痕链 append 无锁、打卡读-改-写丢更新 | ✅ 3/3 |
| P0-C | 审批详情/附件越权、任意管理岗可审批所有单、编辑页绕过禁用会签、插件开关可 GET | ✅ 4/4 |
| P1 | 传输安全配置、登录限流与密码校验器、注册表检查时机、开关表每请求全表查询、菜单权限 N+1、信号订阅无隔离、重新申请非原子、审批列表 N+1 与分页、留痕页全链重算、工作台跨插件查询无守卫、图表计数口径分裂、异常静默吞噬、调休依据过宽、依赖未锁定与零门禁 | ✅ 14/14 |

**明确不在本版**：P0-A（`SECRET_KEY` 回退值、SSO 默认密钥、默认口令、`DEBUG`/`ALLOWED_HOSTS` 默认值）、容器 root 运行与健康检查、`entrypoint.sh` 字符串拼接、`has_perm` 三处口径不一致、模板内联图表 JS 重复。

## 二、设计口径（契约）

| 项 | 决策 |
|---|---|
| 并发保护方式 | 状态判断与写入必须在同一行锁内：`transaction.atomic()` + `Approval.objects.select_for_update().get(pk=…)` 重新取实例，不再信任调用方传入的对象快照 |
| 信号发送时机 | 保持在事务块**内**同步发送（不引入 `transaction.on_commit`）：现有 callback（部门物理删除 / 用户禁用）在 `TestCase` 内必须同步生效，改用 on_commit 会让 184 项既有测试失效；订阅方失败由各自 handler 隔离 |
| 审批操作人 | 服务层强制校验 `operator.pk == approval.approver_id`，超管例外；视图层 `_can_act` 同步收紧，**删除 `or has_perm('approval_approve')` 旁路** |
| 审批可见性 | 申请人 / 审批人 / 会签人 / 抄送人 / 超管；**`approval_view` 是 L3 全员码，不再作为详情与附件的兜底** |
| 越权响应 | 沿用项目惯例：`redirect('index')`（302），不返回 403，保持既有安全测试口径 |
| 用户状态变更 | 唯一入口是 `user_status`（超管直接生效；普通管理员先冻结并发起会签）。编辑页保留 `is_active` 字段用于展示，但非超管改动一律回错误、不落库 |
| 插件开关 | 仅接受 POST；静态 `enabled=False` 的插件在运行中启用仍需重启（边界未变，见第十节） |
| 开关缓存 | 进程内 TTL 30 秒；`PluginSwitch.save()/delete()` 与 `post_delete` 即时失效；**事务内（`connection.in_atomic_block`）直接读 DB**，避免测试回滚后缓存污染 |
| 注册表校验 | 改为 Django 系统检查（id `plugin_host.E001`），在全部 app ready 之后由 `manage.py check` / test / runserver 触发；不再在 `PluginHostConfig.ready()` 里直接调用（那时注册表几乎是空的） |
| 插件计数 | `registry.plugin_counts()` 是唯一口径：静态 `OA_PLUGINS` → DB 开关 → 默认启用；charts 作为 Provider 走同一判定，删除工作台的 `+1` 补丁 |
| 分页 | 审批三类列表统一 25 条/页，模板复用签到详情的分页样式（无新增 CSS） |
| 留痕校验 | 列表/详情用 60 秒快照缓存（键含 `max_id` 与 `count`，追加记录自动换键）；`_verify_snapshot(force=True)` 强制全量 |
| 传输安全 | 默认值保证本地与 `docker compose` 直连 8000 可用；生产由反代终止 TLS 后显式开启 `DJANGO_HTTPS=1`（必要时再加 `DJANGO_SSL_REDIRECT=1`） |
| 登录限流 | 同一「用户名 + `REMOTE_ADDR`」15 分钟内失败 5 次后拒绝（正确密码也先拒），成功登录清零；不信任可伪造的 `X-Forwarded-For` |
| 密码校验 | 所有**显式设置**的新密码过 `AUTH_PASSWORD_VALIDATORS`；新建用户的默认口令路径不变（属 P0-A，未在范围） |
| 依赖与门禁 | 运行依赖精确版本；`pyproject.toml` 定义 ruff 基线；CI 执行 `ruff check` + `manage.py check` + 全量测试 |

## 三、实现

### 3.1 并发与事务

| 文件 | 改动 |
|---|---|
| `plugins/approval/services.py` | 新增 `_locked()`；`submit / approve / reject / start_counter_signature / sign_approve / sign_reject` 全部在 `atomic()` 内取行锁后判断与写入；`approve/reject` 增加操作人校验（`PermissionError('您不是该单据的审批人')`）；`_mark_signed` 改为条件更新 `filter(pk=…, signed=False).update(...)`，影响行数为 0 即「您已签过」；会签终态判定在锁内完成 |
| `plugins/blockchain/models.py` | `append()` 包 `transaction.atomic()`，链尾 `select_for_update()`；`IntegrityError` 回滚后重试一次（重试会重读链尾拿到新 `prev`）；哈希公式与 `verify_chain()` 未改 |
| `plugins/attendance/views.py` | 打卡/补卡在事务内 `select_for_update()` 重读，只 `save(update_fields=[…])` 本次真正变动的字段，签退不再整行覆盖 `check_in`；`status` 仍由模型 `save()` 重算 |
| `plugins/blockchain/apps.py`、`plugins/notify/apps.py` | 全部信号 handler 经 `_safe(label, handler)` / 显式 `try/except` 包一层，失败只 `logger.exception`，不再让留痕或通知故障打断审批与打卡主流程 |

### 3.2 授权边界

| 文件 | 改动 |
|---|---|
| `plugins/approval/views.py` | 新增 `_may_view(user, approval)`（申请人/审批人/会签人/抄送人/超管）；`approval_detail`、`approval_attachment` 改用它，**移除 `approval_view` 兜底**；`_can_act` 普通单改为「审批人本人或超管」；POST 分支捕获 `(ValueError, PermissionError)` |
| `plugins/user/views.py` | `user_edit` 检测 `is_active in form.changed_data`：非超管 → `form.add_error` 并重新渲染；超管 → 保存后补 `permission_frozen`、`user_disabled`、`user_status_changed` 信号，与 `user_status` 口径一致 |
| `plugins/workspace/views.py` | `switch_toggle` 增加 `@require_POST` |

### 3.3 性能与可观测

| 文件 | 改动 |
|---|---|
| `plugin_host/registry.py` | `get_plugin_switches()` 快照缓存（TTL 30s，`values_list`，事务内直读）+ `invalidate_plugin_switch_cache()`；新增 `plugin_enabled()` / `plugin_counts()`；`get_menus()` 一次取权限码集合（基线 + 个人 + 角色），菜单判定只查内存 |
| `plugins/workspace/models.py` | `PluginSwitch.save()/delete()` 覆写并失效缓存，另挂 `post_delete` 兜住 `QuerySet.delete()` |
| `plugin_host/discover.py`、`apps.py` | `check_registry` 改为系统检查 + `assert_registry_ok()`；`ready()` 只负责 import 注册 |
| `plugin_host/charts.py`、`context_processors.py` | `chart_switch_enabled` 委托 `plugin_enabled('charts')`；`except Exception` 收窄为 `(ImportError, LookupError, OperationalError, ProgrammingError)` 并记 warning |
| `plugin_host/workbench.py`、`views.py` | 每个跨插件区块补「模型存在 + 插件启用」守卫与 DB 异常降级；`enabled_count`/`plugin_total` 统一走 `plugin_counts()` |
| `plugins/approval/views.py` | 三类列表 `select_related('applicant','approver')` + `Paginator(25)`；`_overtime_choices` 限 `status=APPROVED` 且 `created_at` 近 365 天；重新申请流程包 `atomic()` + 源单 `select_for_update()` 二次校验 |
| `plugins/blockchain/views.py` | 新增 `_verify_snapshot(force=False)`：按 `(max_id, count)` 缓存 60 秒 |

### 3.4 传输安全与登录

| 文件 | 改动 |
|---|---|
| `plugin_host/settings.py` | 新增 `HTTPS_ENABLED` 派生配置：`SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` / `SECURE_HSTS_SECONDS`（含子域与 preload）随 `DJANGO_HTTPS` 开启；`SECURE_SSL_REDIRECT` 随 `DJANGO_SSL_REDIRECT`；恒定 `SESSION_COOKIE_HTTPONLY`、`SameSite=Lax`、`SECURE_PROXY_SSL_HEADER` |
| `plugins/auth/views.py` | 失败计数（`auth:login-fail:<sha256(username|ip)>`）、阈值 5 次 / 900 秒；超限返回登录页 + 「尝试次数过多，请稍后再试」；成功登录 `cache.delete` |
| `plugins/user/forms.py` | `PasswordForm.clean` 与 `UserForm.clean` 调用 `validate_password`（仅显式密码，且 `can_change_password`） |

### 3.5 工程化

| 文件 | 改动 |
|---|---|
| `requirements.txt` | 精确版本：`django==5.2.18` / `mysqlclient==2.3.0` / `gunicorn==26.2.0` / `whitenoise==6.12.0` |
| `requirements-dev.txt` | 新增；CI 用（不含 mysqlclient，避免 C 编译依赖） |
| `pyproject.toml` | 新增；ruff 基线 `E4/E7/E9/F/I/B/DJ`，排除 `venv/dist/staticfiles/docs/thesis/tools/migrations` |
| `.github/workflows/ci.yml` | 新增；`ruff check` → `manage.py check` → `manage.py test` |
| 代码库 | 落地门禁时清理 57 处历史违规（52 处自动修复：导入排序 39、未用导入 12 等），此后 `ruff check .` 必须为 0 |

## 四、配置项变更

| 变量 | 默认 | 作用 |
|---|---|---|
| `DJANGO_HTTPS` | `0` | `1` = 会话/CSRF Cookie 仅 HTTPS + 开启 HSTS |
| `DJANGO_SSL_REDIRECT` | `0` | `1` = 全站 301 到 HTTPS（反代已跳转时不要重复开） |
| `DJANGO_HSTS_SECONDS` | `31536000` | HSTS 有效期，仅 `DJANGO_HTTPS=1` 时生效 |

`docker-compose.yml` 透传上述三个变量，`.env.example` 补充说明与生产建议。

## 五、测试

新增 64 项（259 → 323），全量 `manage.py test` 通过：

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `plugin_host/tests_registry.py` | 19 | 系统检查冲突检出、菜单权限集合与 `has_perm` 逐条判定等价（匿名/基线/角色/个人/超管/冻结/停用）、开关缓存失效（create/delete/`QuerySet.delete`/TTL） |
| `plugin_host/tests_workbench.py` | 7 | 停用插件或模型缺失时首页降级不 500、计数口径一致 |
| `plugins/approval/tests_authz.py` | 10 | 陌生员工读他人详情/附件被拒、抄送人与会签人可读、非 approver 的管理岗不能操作、超管可操作、分页 25/5、调休依据过滤 |
| `plugins/blockchain/tests_chain.py` | 6 | 链连续、同 payload 不冲突、唯一键重试、handler 报错不影响上游 |
| `plugins/blockchain/tests_views.py` | 3 | 快照复用、追加换键、`force` 绕过缓存 |
| `plugins/attendance/tests_atomic.py` | 6 | 同日二次打卡单行、签退保留 `check_in`、陈旧快照不覆盖、迟到/早退/补卡口径 |
| `plugins/user/tests_security.py` | 8 | 传输安全默认值、弱密码被拒、编辑页改状态被拦（禁/启用）、超管经编辑禁用生效 |
| `plugins/auth/tests_ratelimit.py` | 3 | 5 次后锁定、成功清零、按用户隔离 |
| `plugins/workspace/tests.py`（追加） | 2 | GET 切换返回 405、直接 ORM 写开关即时生效 |

既有测试只改了 1 处语义：`tests_v155.test_comp_with_overtime_choice` 的加班单需要 `status=APPROVED`（调休依据收紧后的正确前置条件）。

## 六、验收记录（2026-10-27）

| 项 | 结果 |
|---|---|
| `python manage.py test` | **Ran 323 tests — OK** |
| `ruff check .` | All checks passed |
| `python manage.py check` | no issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected（本版零迁移） |
| `DJANGO_HTTPS=1 DJANGO_SSL_REDIRECT=1 manage.py check --deploy` | 5 条警告 → **1 条**（仅剩 `SECRET_KEY`，属 P0-A） |
| `docker compose up -d --build` | web 重建重启，db 未动；`No migrations to apply`，collectstatic 131 文件，3 worker |
| 容器内冒烟 | 登录页 200、`/` 302、静态资源 200；`/`、审批三页、留痕、插件开关、考勤、公告、消息中心共 9 页全部 200（`DEBUG=0`，MySQL） |

## 七、已知边界与后续

1. **SQLite 下 `select_for_update()` 是 no-op**：行锁只在 MySQL 生产生效；本机并发用例验证的是「陈旧实例二次提交」这类可确定性场景，不是真线程并发。
2. **留痕 `append` 只重试一次**：持续高并发同 payload 时第二次仍抛 `IntegrityError`，该条留痕会丢（不阻断业务）。
3. **开关缓存对 `QuerySet.update()` 无感**：绕过 `save()`/信号的写入最多 30 秒陈旧（现有代码未使用）；开启 `ATOMIC_REQUESTS` 会失去该缓存收益。
4. **留痕校验快照**：原地改库最多延迟 60 秒被列表发现，需要即时结论时用 `_verify_snapshot(force=True)`。
5. **登录限流用默认 LocMem 缓存**：多 worker 各自计数；与 SSO 防重放同源问题，需共享缓存（建议随 P0-A 一并处理）。
6. **静态 `enabled=False` 的插件运行中启用仍需重启**：路由在启动时静态 include，边界未变。
7. **未做**：P0-A 四项部署默认值、容器非 root 与健康检查、`entrypoint.sh` 环境变量拼接、`has_perm` 三处口径不一致、模板内联图表 JS 重复与 163 处 inline style。
