# 插件开发文档：v1.7.7 限流计数原子化（P2，首项）+ 认证后端插件化

> **【前置】P2 的并发验证只认容器 MySQL。** 本地测试跑 sqlite，而 `select_for_update` 在 sqlite 上是
> **静默退化**：`connection.features.has_select_for_update = False`，`compiler.as_sql` 里
> `if self.query.select_for_update and features.has_select_for_update:` 整块被跳过——**不加 `FOR UPDATE`、也不抛错**
> （实测：切片 + `select_for_update()` 在 autocommit 与 `atomic()` 内都不报错，生成的 SQL 里没有 `FOR UPDATE`）。
> 同一写法项目里早有先例：`roadmap.md` 修复项第 2 条（v1.7.1 区块链链尾锁）已标注「SQLite 下为 no-op」。
> 所以：①**并发语义只在容器 MySQL 上验收**；②sqlite 上的用例只验证「顺序语义 / 窗口 / 清零 / 阈值」，注释里写明
> 「本用例不验证锁」——sqlite 单写锁下的「不丢计数」是数据库级串行，不是我们的锁，不能当证据。

> 关联：`plugins/auth`（登录限流）、`plugin_host/settings.py`（`AUTHENTICATION_BACKENDS`）、新增 `plugin_host/auth_backends/`
> 版本：v1.7.7 · 文档日期：2026-11-10
> 状态：**✅ 已实现**（403 项测试全绿 + 容器 MySQL 并发验收；见 §五）
> 基线：tag `v1.7.6`（387 项测试）
> 编号说明：按 roadmap 原文执行（v1.7.7 = P2 首项 + 认证后端插件化）；审计字段已改号 **v1.7.8**（`docs/plugin-dev-v178.md`，草案已按裁定修好）；越权语义统一 **v1.7.9（待定）**。

## 一、问题复核（实测）

### 1.1 P2：限流计数在 3 worker 下丢更新

v1.7.3 已经把缓存换成共享 `DatabaseCache`，但计数仍是 `cache.get` + `cache.set` 两步：

```python
# plugins/auth/views.py（现状）
def _is_locked(request, username):
    return (cache.get(_fail_cache_key(request, username)) or 0) >= LOGIN_FAIL_LIMIT

def _record_failure(request, username):
    key = _fail_cache_key(request, username)
    failures = (cache.get(key) or 0) + 1        # ← 读
    cache.set(key, failures, LOGIN_FAIL_WINDOW)  # ← 写（中间可被别的 worker 插入）
    return failures
```

v1.7.3 交付前自检实测：**6 路并发全部计错，最终计数 2 / 4 / 4**（串行口径应封顶 5 并拦掉第 6 次），单轮突发可多试 2~4 次。`DatabaseCache` 未覆盖 `incr`，继承的 `BaseCache.incr` 同样是 `get` + `set`，且 `set` 不传 timeout 会把窗口重置成默认 TTL —— 两条都不能用。

### 1.2 认证后端：目前只有 Django 默认 ModelBackend

- `settings.py` 未配置 `AUTHENTICATION_BACKENDS` → 走 `django.contrib.auth.backends.ModelBackend`（只认 username）。
- `plugins/sso/views.py:87` 显式传 `backend='django.contrib.auth.backends.ModelBackend'`（SSO 登录不依赖列表顺序，但要求该 backend 仍在列表里）。
- 框架事实（`inspect` 5.2.18）：`django.contrib.auth._get_backends()` **每次调用都读 `settings.AUTHENTICATION_BACKENDS`**（无缓存），列表为空时 `raise ImproperlyConfigured`；`authenticate()` 按列表顺序逐个尝试，第一个返回非 None 的用户生效，并把 `user.backend` 设为该 backend 路径（`login()` 依赖这个）。
- `plugins/auth/migrations/` 目前只有空 `__init__.py`、`models.py` 只占位注释 → 加 `LoginFailureCounter` 会生成该插件第一个迁移 `0001_initial.py`（只应含计数表一张）。

## 二、设计口径（契约）

### 2.1 P2：独立计数表 + `select_for_update` + 单条 UPDATE

```python
# plugins/auth/models.py（app label 是 plugin_auth，迁移目录在 plugins/auth/migrations/）
class LoginFailureCounter(models.Model):
    """登录失败计数（v1.7.7）：key = sha256(用户名小写+IP)[:32]，与旧缓存键同源。"""
    key = models.CharField('计数键', max_length=64, unique=True)
    count = models.PositiveIntegerField('失败次数', default=0)
    window_started_at = models.DateTimeField('窗口开始时间')

    class Meta:
        db_table = 'auth_login_failure_counter'
        verbose_name = '登录失败计数'
```

写入（`plugins/auth/views.py`，实际实现）：

```python
def _bump_counter(key):
    now = timezone.now()
    cutoff = _window_cutoff(now)
    # 关键（实测踩过 InnoDB 1213 死锁）：**只对已存在的行加行锁**。
    # 对不存在的 key 直接 select_for_update() 会加 gap 锁，与并发 INSERT 互相等待 → 死锁。
    if not LoginFailureCounter.objects.filter(key=key).exists():
        try:
            LoginFailureCounter.objects.create(key=key, count=1, window_started_at=now)
            return 1
        except IntegrityError:
            pass                                  # 并发下别人先插入 → 落到按已存在处理

    with transaction.atomic():
        # 约束 1：select_for_update() 的 queryset 不能带切片 —— 支持 FOR UPDATE 的后端上
        #         「FOR UPDATE + LIMIT/OFFSET」会 NotSupportedError（sqlite 上被静默忽略，不易发现）
        # 约束 2：必须在 transaction.atomic() 内调用，否则 MySQL 抛 TransactionManagementError
        counter = LoginFailureCounter.objects.select_for_update().get(key=key)
        if counter.window_started_at <= cutoff:   # 窗口过期 → 重置
            counter.count = 1
            counter.window_started_at = now
        elif counter.count >= LOGIN_FAIL_LIMIT:   # 已达阈值：不累加、不刷新窗口（计数封顶）
            return counter.count
        else:
            counter.count += 1
        counter.save(update_fields=['count', 'window_started_at'])
        return counter.count


def _record_failure(request, username):
    """失败计数跨 worker 不丢更新；InnoDB 死锁（正常并发现象）重试最多 3 次。"""
    key = _fail_key(request, username)
    for attempt in range(3):
        try:
            return _bump_counter(key)
        except OperationalError as exc:
            if not _is_deadlock(exc) or attempt == 2:
                raise
```

读：`filter(key=key).values_list('count', 'window_started_at').first()`；`window_started_at <= cutoff` 视为 0（读路径不需要锁）。
成功登录：`filter(key=key).delete()`（替代 `cache.delete`）。

**为什么选 A（`select_for_update`）而不是「单条 `UPDATE ... CASE`」**（上一轮我提议 B，理由不成立，已撤回）：

| | A. `select_for_update` + `atomic`（选它） | B. 单条 `UPDATE ... CASE` |
|---|---|---|
| sqlite 分支 | **不需要**（自动静默退化） | 不需要 |
| 窗口重置 | Python 里比时间，可读 | SQL `Case/When` 比时间，难读且要传 cutoff |
| 是否超阈值 | 拿到行直接比 `count` | UPDATE 不返回新值，还得再 `get()` 一次 |
| 行不存在竞态 | `create` + `IntegrityError` 重试 | 同左 |
| 与项目既有写法 | 与 v1.7.1 区块链链尾锁一致 | 项目内无先例 |
| 每次失败查询数 | 2（SELECT + UPDATE） | 2（UPDATE + SELECT） |

**保留 `LOGIN_FAIL_LIMIT=5` / `LOGIN_FAIL_WINDOW=900` 不变**（修存储，不修阈值）。

### 2.2 认证后端插件化：`OA_AUTH_BACKENDS` + 契约校验 + 示例后端

```python
# settings.py
OA_AUTH_BACKENDS = [
    'plugin_host.auth_backends.username_or_email.UsernameOrEmailBackend',
]
AUTHENTICATION_BACKENDS = [*OA_AUTH_BACKENDS, 'django.contrib.auth.backends.ModelBackend']
```

- **列表语义**（不是「单选引擎」）：认证后端是**有序链**，`authenticate()` 逐个尝试、第一个成功的生效。所以这里用「dotted path 列表」而不是 theme/chart 那种「目录 + 单 key 选择」——发现机制对有序链没有收益。加一行 = 多一种登录方式，与 `tech-stack-and-architecture.md` 的承诺一致。
- **`ModelBackend` 永远排最后**：保证「默认后端仍可用」；SSO 显式传的那个路径也仍在列表里。
- **契约校验必须是纯函数**（`plugin_host/auth_backends/registry.py`）：
  ```python
  def validate_auth_backends(paths) -> None:   # 不合格 → ImproperlyConfigured
  ```
  `apps.ready()` 只负责调它。理由：`ready()` 每个进程只跑一次，`override_settings` 不会重新触发它，
  写在 `ready()` 里的校验**测试测不到**（只能 mock，那是自欺）。用例直接打这个纯函数。
  校验内容：能 import、是 `BaseBackend` 子类、**覆盖了** `authenticate` 与 `get_user`（`BaseBackend.get_user` 默认 `raise NotImplementedError`）。
- **空列表必须放行**：`OA_AUTH_BACKENDS = []` → `AUTHENTICATION_BACKENDS` 只剩 `ModelBackend`，**不报错**。
  否则新环境第一次 `migrate` 就死在校验里。
- **示例后端**（无外部依赖）：`UsernameOrEmailBackend(ModelBackend)` —— `authenticate()` 先按 `username` 精确匹配，未命中再按 `email__iexact` 匹配；两条命中路径都必须过 `self.user_can_authenticate(user)`（`is_active` 检查）。
  **这是权限绕过红线**：`ModelBackend.authenticate()` 内部会 `user_can_authenticate`，自定义后端若只做「查到用户就返回」，**被禁用的用户能直接登录**。验收里有专门一条用例钉住。`get_user` 直接继承。
- **不改 SSO**：`plugins/sso/views.py:87` 显式 backend 的写法保留（SSO 账号不可用密码，不属于「换一种密码认证」）。
- **停用方式**：`OA_AUTH_BACKENDS = []` → 只剩 `ModelBackend`，email 登录即失效，username 照常。

### 2.3 与限流的联动（必须验）

登录失败计数挂在 `login_view` 上，与「用哪个 backend 认证」无关：示例后端启用后，**email 连续错 5 次**同样要触发锁定。这是 P2 与认证插件化同版交付要额外覆盖的一条。

## 三、实现清单（逐文件；确认后按序小步改）

**P2（先做）**
1. `plugins/auth/models.py`：`LoginFailureCounter`。
2. `plugins/auth/views.py`：`_record_failure` / `_is_locked` / 成功分支改走该表（删 cache 依赖）；`_fail_cache_key` 改名 `_fail_key`（只是标识符，键值算法不变：`sha256(用户名小写+IP)[:32]`）。
3. `plugins/auth/migrations/0001_initial.py`：`makemigrations auth` 生成后开文件确认**只有 `LoginFailureCounter` 一张表**。
4. `plugins/auth/tests_ratelimit.py`：保留既有 3 条（串行阈值 / 清零 / 用户隔离），新增 4 条（并发自增 / 窗口过期重置 / 成功清零删行 / 超阈值拦截）。

**认证后端（后做）**

5. `plugin_host/auth_backends/__init__.py` + `registry.py`（契约校验 + 解析路径）。
6. `plugin_host/auth_backends/username_or_email.py`：示例后端。
7. `plugin_host/settings.py`：`OA_AUTH_BACKENDS` + `AUTHENTICATION_BACKENDS`（组合式）。
8. `plugin_host/apps.py`：`ready()` 里跑契约校验。
9. 测试 `plugin_host/tests_auth_backends.py`（见 §四）。
10. 文档：本文件定稿 + `docs/plugin-dev-sso.md` 补一句「SSO 显式 backend 不受插件化影响」+ roadmap / README / constraints。

## 四、测试记录（实际新增 16 条：P2 4 条 + 认证后端 12 条，387 → 403）

**P2（`plugins/auth/tests_ratelimit.py`）**

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_failure_counter_increments` | 连续两次 `_record_failure` → `count == 2`、`window_started_at` 不变（**本用例不验证锁**：sqlite 上 `select_for_update` 被静默忽略，并发证据只看容器 MySQL） |
| 2 | `test_window_expiry_resets_counter` | 把 `window_started_at` 调到 901 秒前 → 下一次失败后 `count == 1`、窗口时间被刷新 |
| 3 | `test_success_deletes_counter_row` | 失败 3 次后正确登录 → 该 key 的行被删除 |
| 4 | `test_threshold_blocks_even_with_correct_password` | 直接塞 `count=5` → 正确密码仍返回「尝试次数过多」，且不建登录态 |

**认证后端（`plugin_host/tests_auth_backends.py`）**

| # | 用例 | 断言 |
|---|---|---|
| 5 | `test_email_login_works_with_example_backend` | 启用示例后端 → 用 email 登录成功（302） |
| 6 | `test_username_login_still_works` | 同一后端下 username 登录仍成功（不影响既有路径） |
| 7 | `test_disabling_provider_keeps_default_backend` | `OA_AUTH_BACKENDS=[]` → email 登录失败（停在登录页），username 仍成功 |
| 8 | `test_invalid_backend_path_fails_fast` | 直接调 `validate_auth_backends([...])`：不存在的路径 / 非 `BaseBackend` 子类 → 抛 `ImproperlyConfigured`；空列表 → **不抛** |
| 9 | `test_disabled_user_cannot_login_via_custom_backend` | 自定义后端命中一个 `is_active=False` 的用户 → 返回 None（登录失败），**不允许绕过 is_active** |

## 五、验收记录（2026-11-10 实测）

### 5.1 迁移（第一批交付物）

`plugin_auth/0001_initial.py` 只有一张表（`makemigrations` 输出 `+ Create model LoginFailureCounter`）：
`id` / `key`(unique) / `count` / `window_started_at`，`db_table = auth_login_failure_counter`。

容器 `migrate` 后表结构（MySQL 8.0）：`PRIMARY KEY (id)`、**`UNIQUE KEY key`**、`count int unsigned`。
回滚往返：`migrate plugin_auth zero` → 表数 **0**；`migrate plugin_auth` → 表数 **1**。

### 5.2 并发计数（容器 MySQL，3 worker）

6 路并发错密码，连续 5 轮：

```
第 1 轮: 计错 4 / 被拦 2 | 库内计数 = [5]
第 2 轮: 计错 4 / 被拦 2 | 库内计数 = [5]
第 3 轮: 计错 4 / 被拦 2 | 库内计数 = [5]
第 4 轮: 计错 4 / 被拦 2 | 库内计数 = [5]
第 5 轮: 计错 4 / 被拦 2 | 库内计数 = [5]
期间容器日志出现 500 / 死锁的条数 = 0
```

对照轮：`GUNICORN_WORKERS=1` 起容器，同样 6 路并发 → **库内计数 = [5]**（与 worker 数无关）。
串行追加第 7 次 → 被拦（「尝试次数过多」），计数仍为 5（封顶）。

> 对比 v1.7.3 的 2/4/4：现在稳定 5，且 0 次 500。
> 「计错 4 / 被拦 2」而不是 5/1 是语义使然：第 5 次失败把计数推到阈值，**当次就回锁定提示**；
> 另一路在检查阶段已看到锁定。不是丢计数。

### 5.3 实现期发现并修掉的真缺陷：InnoDB gap 锁死锁

第一版按 `select_for_update().filter(key=key).first()` 先锁再插，容器实测出现
`(1213, 'Deadlock found when trying to get lock')` → 500。原因：对**不存在**的 key 做
`SELECT ... FOR UPDATE` 会加 gap 锁，与并发 INSERT 互相等待。
修法：先无锁 `exists()`；不存在直接 INSERT（唯一键兜并发），只有行存在时才
`select_for_update()` 取记录锁；外层加 3 次死锁重试。修后 5 轮 + 单 worker 对照 **0 次 500**。

### 5.4 认证后端

```
OA_AUTH_BACKENDS = ['plugin_host.auth_backends.username_or_email.UsernameOrEmailBackend']
AUTHENTICATION_BACKENDS = [<同上>, 'django.contrib.auth.backends.ModelBackend']
validate_auth_backends(...) -> [<UsernameOrEmailBackend object>]        # 容器内实测通过
```

容器 HTTP 冒烟：临时把 `admin` 的 email 设为 `admin-probe@corp.local` → 用**邮箱 + 密码**登录 → **302 到 /**；
随后把 email 恢复为空（原值）。

### 5.5 门禁

`check` 无问题 / `ruff` All checks passed / **Ran 403 tests OK**（387 + 16）。
随 P2 契约更新的既有用例：`plugin_host/tests_cache.py` 中「登录失败计数落在共享存储」由
「查 `constellatio_cache` 的 `auth:login-fail:` 行」改为「查新计数表」——计数迁出缓存后原断言必然为 0，
属**契约变更同步**，不是放宽断言。

## 六、不做 / 已知边界

- 不做 LDAP / OAuth（要新依赖，需批准）；示例后端只用 username-or-email。
- 不改 `LOGIN_FAIL_LIMIT` / `LOGIN_FAIL_WINDOW`；不改 SSO 的显式 backend。
- sqlite 上不验收并发（前置说明）；本地用例只跑顺序语义。
- 计数表不写审计字段（它是基础设施表，且本版审计字段在 v1.7.8）。

## 七、待办观察

1. 计数表的清理：成功登录删行、窗口过期靠「下次写入时重置」，**没有定期清理**——长期会有「失败过但再没来过」的孤儿行（键空间按 用户名+IP 哈希，规模可控，后续可加管理命令）。
2. `select_for_update` 在 sqlite 上静默退化（不加 `FOR UPDATE`、不抛错），所以**本地永远验证不到锁语义**；任何「这次并发安全了」的结论都必须在 MySQL 上复验（与 v1.7.1 区块链链尾锁同一口径）。
3. 示例后端是否要在管理页提供开关（当前只能改 settings）。
4. 测试里 `override_settings(AUTHENTICATION_BACKENDS=...)` 是可行的（`_get_backends` 每次读 settings），但**运行时**换列表不适合当生产开关，重启才算数。
