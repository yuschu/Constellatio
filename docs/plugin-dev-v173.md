# 插件开发文档：v1.7.3 共享缓存（登录限流 / SSO 防重放跨 worker 成立）

> 关联插件：auth（登录失败限流）、sso（Ticket 防重放）、blockchain（链校验快照缓存）、容器（settings / entrypoint）
> 版本：v1.7.3 · 文档日期：2026-11-10
> 状态：**✅ 已实现**（357 项测试全绿 + 3 worker 容器验收 + 生产 MySQL 唯一键实测）
> 基线：v1.7.2（tag `v1.7.2`，352 项测试全绿，Django 5.2.18 / Python 3.13.16）

## 一、需求

1. **登录限流在 3 worker 下失效**：`entrypoint.sh` 默认 `--workers 3`，`plugins/auth/views.py` 的 `LOGIN_FAIL_LIMIT=5 / LOGIN_FAIL_WINDOW=900` 计数落在每进程独立的 LocMemCache 里，实际要连错 15 次才拦。
2. **SSO 防重放在 3 worker 下失效**：`plugins/sso/ticket.py` 的 `cache.add` 去重标记同样进程内，同一 Ticket 打到不同 worker 可重复使用（源码注释已自陈"多 worker 需共享缓存"）。
3. **修的是存储共享，不是阈值**：把默认缓存换成数据库缓存（`DatabaseCache`），让 `add()` 的唯一键冲突成为跨进程的"只有第一个写入者成功"，不引入 Redis。

## 二、问题复核（本机实测，2026-11-10）

| 复核项 | 实测结果 | 证据来源 |
|---|---|---|
| `plugin_host/settings.py` 是否配了 `CACHES` | **没有**：`grep -n "CACHES\|LocMem\|cache" plugin_host/settings.py` 无输出 | 仓库当前代码 |
| 运行时实际后端 | `settings.CACHES = {'default': {'BACKEND': '...locmem.LocMemCache'}}`，`type(caches['default']).__name__ == 'LocMemCache'` | Django 默认值 `venv/Lib/site-packages/django/conf/global_settings.py:515-519`；`max_entries=300`、`default_timeout=300` |
| 跨进程是否可见 | 进程 A `cache.set('probe-share','A',60)` → `A`；进程 B `cache.get('probe-share')` → **`None`** | 两次独立 `manage.py` 进程实测 |
| `cache` 调用点全清单 | `plugins/auth/views.py:36,41,42,60`（get/set/delete）、`blockchain/views.py:36,40`（get/set，60s 快照）、`plugins/sso/ticket.py:79`（**唯一一处 `cache.add`**） | `grep -rn "cache\." --include=*.py` |
| worker 数 | `entrypoint.sh:30` `--workers "${GUNICORN_WORKERS:-3}"`；`docker-compose.yml` `GUNICORN_WORKERS: ${GUNICORN_WORKERS:-3}` | 代码 |
| 缺缓存表的后果 | `DatabaseCache` 未建表时 `cache.add()` **直接抛** `OperationalError: no such table: constellatio_cache`（不是返回 False） | 用临时 settings 实测（见 §三 事实 4） |

结论：两条"后果"属实，且**根因是同一个**——默认缓存后端是进程内的。

## 三、框架事实（本次用 `inspect.getsource` 现读 Django 5.2.18，不靠记忆）

**事实 1 —— `add()` 的唯一性来自主键冲突**

`DatabaseCache.add(key, value, timeout, version)` = `make_and_validate_key(...)` + `self._base_set("add", key, value, timeout)`。

`_base_set()` 在 `mode="add"` 下的三条分支（原文语义）：

| 情形 | 执行 | 返回 |
|---|---|---|
| 表中无该 key | `INSERT INTO <table> (cache_key, value, expires)` | `True` |
| 有该 key 且 `current_expires < now`（已过期） | `UPDATE ... SET value, expires` | `True` |
| 有该 key 且未过期 | 落到 `elif mode != "touch"` 分支 → 再 `INSERT` 同一 `cache_key` → **唯一键冲突** | 被 `except DatabaseError: return False` 捕获 → **`False`** |

"已存在且未过期"并不是查一下再返回 False，而是**靠 INSERT 撞主键**——所以并发下谁先提交谁 `True`，其余全部 `False`。这正是跨进程语义成立的原因，且不依赖 Redis。

**事实 2 —— 唯一键由建表语句保证**

`manage.py createcachetable` 建表字段：`cache_key VARCHAR(255) PRIMARY KEY`、`value TEXT`、`expires DATETIME`（带索引）；命令**幂等**（表已存在则打印 `already exists` 后返回），表名取 `CACHES[...]['LOCATION']`。

**事实 3 —— 默认 `MAX_ENTRIES=300` 会淘汰未过期条目**

`_base_set` 开头先 `SELECT COUNT(*)`，超过 `_max_entries` 就 `_cull()`：先删已过期行；仍超限则按 `cache_key` 排序删掉 `1/CULL_FREQUENCY`（默认 3）——**这是"未过期也可能被删"**。若不调高，防重放标记可能在 Ticket 过期前被挤掉，重放窗口被悄悄重新打开。本版把 `MAX_ENTRIES` 调到 10000（见 §四）。

**事实 4 —— 缺表/DB 不可用时是抛异常，不是放行**

`_base_set` 中 `cursor.execute("SELECT COUNT(*) FROM <table>")` 位于 `try` 之外，所以缺表或数据库不可用时 `OperationalError` 会**向上冒泡**；返回 `False` 只覆盖 `try` 内的 `DatabaseError`。实测（临时 settings + 未建表的 sqlite）：`cache.add()` → `OperationalError: no such table: constellatio_cache`。

**事实 5 —— 生产 MySQL 的字段宽度可用**

`cache_key VARCHAR(255) PRIMARY KEY` 在 MySQL 8 默认 `utf8mb4` + InnoDB DYNAMIC 行格式下占 1020 字节，低于 3072 字节索引上限；若目标机被强制成 COMPACT/REDUNDANT 行格式才可能建表失败（本项目 compose 用 `mysql:8.0` 默认配置，实测建表通过，见 §七 第 4 条）。

## 四、设计口径（契约）

| 项 | 决策 | 理由 |
|---|---|---|
| 缓存后端 | `django.core.cache.backends.db.DatabaseCache`，`LOCATION = 'constellatio_cache'`，`TIMEOUT = 900` | 复用已有 MySQL/sqlite，零新依赖；900 与 `LOGIN_FAIL_WINDOW` 同口径（调用点各自显式传 timeout，默认值只是兜底） |
| 容量 | `OPTIONS = {'MAX_ENTRIES': 10000, 'CULL_FREQUENCY': 3}` | 默认 300 会淘汰未过期标记（事实 3）；500 人规模：限流键 ≤ 人数 + 5 分钟内 Ticket 标记数，万级留足余量 |
| 建表时机（容器） | `entrypoint.sh`：`migrate` 之后、`collectstatic` 之前 `python manage.py createcachetable` | 建表依赖数据库连通；放 collectstatic 前后皆可，但必须在 gunicorn 起之前，否则首个请求即 500 |
| 建表时机（本地） | README「本地开发」步骤补 `python manage.py createcachetable` | 新开发者第一条会踩的坑：不建表登录页直接 500（事实 4） |
| 建表时机（测试） | 新增 `plugin_host/test_runner.py`：`setup_databases()` 之后调 `createcachetable`；`settings.TEST_RUNNER` 指向它 | 已实测：换成 DatabaseCache 后跑既有用例会因缺表报错；不建表就无法在不改测试的前提下保住 352 |
| `add()` 失败语义 | **保持 fail-closed**：`if not cache.add(...)` → 拒绝 | 唯一键冲突 = 抢占失败 = 重放；DB 故障同样落入 False/异常，一律不放行 |
| 缺表 / DB 不可用 | **不 try/except 吞异常**，让 `OperationalError` 冒泡 | 违反"禁吞异常"；且冒泡方向仍是拒绝（500），不是放行 |
| 阈值 | `LOGIN_FAIL_LIMIT=5` / `WINDOW=900` **不动** | 修存储，不修阈值（禁止项） |
| 依赖 | 不新增任何运行时依赖 | 禁止项 |

## 五、实现清单（逐文件、逐函数；确认后按此顺序小步改）

1. **`plugin_host/settings.py`**（在 `DATABASES` 段之后、"认证与插件化配置"段之前新增一段）
   - 新增 `CACHES`；新增 `TEST_RUNNER = 'plugin_host.test_runner.CacheTableTestRunner'`。
   - 注释写清：这是"登录限流 / SSO 防重放跨进程成立"的唯一来源，以及 `MAX_ENTRIES` 与 cull 的关系。
2. **`plugin_host/test_runner.py`**（新文件）
   - `class CacheTableTestRunner(DiscoverRunner)`：`setup_databases(**kwargs)` → `super()` → `call_command('createcachetable', verbosity=0)` → 返回 `old_config`。
   - 判定逻辑：只对 `BaseDatabaseCache` 实例建表（`createcachetable` 自身已按后端类型过滤，命令幂等，重复跑安全）。
3. **`entrypoint.sh`**（第 9 行 `migrate` 与第 12 行 `collectstatic` 之间插入）
   - `echo "[entrypoint] createcachetable"` + `python manage.py createcachetable`。
4. **`README.md`**（本地开发代码块，`python manage.py migrate` 之后）
   - 补 `python manage.py createcachetable` 一行 + 一句说明（不建表登录会 500）。
5. **`plugins/sso/ticket.py`**（只改注释，不改判定）
   - 第 77 行注释改为"TTL 内同一 Ticket 只允许使用一次（v1.7.3 起走共享 DatabaseCache，跨 worker 成立）`；`if not cache.add(...)` 的 fail-closed 分支保持原样。
6. **`plugin_host/tests_cache.py`**（新测试文件，容器层，不 import 插件）
   - 见 §六。
7. **文档同步**：本文件定稿 + `docs/roadmap.md`（v1.7.3 行 + 状态行）+ `README.md` 状态行 + `docs/constraints-and-acceptance.md` 进度行。

## 六、测试计划（只增不减，不新增 skip、不放宽断言）

新增（预计 5 条，落在 `plugin_host/tests_cache.py`）：

| # | 用例 | 断言要点 |
|---|---|---|
| 1 | `test_default_cache_is_database_backend` | `settings.CACHES['default']['BACKEND']` 是 `...db.DatabaseCache`；`caches['default']` 实例是 `DatabaseCache`；`LOCATION == 'constellatio_cache'` |
| 2 | `test_shipped_cache_config_has_culling_headroom` | `MAX_ENTRIES >= 10000`（防"默认 300 挤掉未过期标记"回归）；`default_timeout == 900` |
| 3 | `test_add_is_first_writer_wins` | 新键 `add` → `True`；同键再 `add` → `False`；用**独立连接的原始 INSERT** 复现唯一键冲突，断言抛 `IntegrityError` 且 `isinstance(exc, DatabaseError)`（即 `_base_set` 的 except 分支能接住） |
| 4 | `test_add_reclaims_expired_key` | 先 `set(key, v, timeout=0)`（expires=now，立即过期）→ `add` → `True`：证明"过期可覆盖"分支不削弱 §四 的安全口径 |
| 5 | `test_login_failures_land_in_shared_cache_table` | 走 `/plugins/auth/login/` 连错 3 次，直接查 `constellatio_cache` 表里 `auth:login-fail:` 前缀的行数 > 0：证明计数确实落在**共享存储**而非进程内 dict |

不变（回归保护，不改断言）：`plugins/auth/tests_ratelimit.py`（5 次后第 6 次被拦、成功清零、按用户名隔离）、`plugins/sso/tests.py`（重放拒绝等）、`plugins/blockchain/tests_views.py`（快照缓存）、`plugins/approval/tests_authz.py`。

> 说明：`test_add_is_first_writer_wins` 覆盖"唯一键冲突被 `except DatabaseError` 接住"这条**机械化路径**；真实两进程抢同一键的**并发**证据按 §七 第 2、4 条现场跑并贴进文档，不塞进自动化用例（sqlite 并发写会随机 `database is locked`，放进套件会让门禁不稳定）。

## 七、验收方案（逐条对应负责人 5 条，全部贴证据进本文档 §八）

1. **本地两次 `add`**：`createcachetable` → `manage.py shell` 连调 `cache.add('k','v')` → 期望 `True` / `False`（sqlite）。
2. **并发抢同一键**：两个独立 OS 进程（非线程）同时 `cache.add` 同一 key → 期望恰好一个 `True`；记录 sqlite 下 loser 的失败类型（主键冲突 vs `database is locked`）与 MySQL 下的对比。
3. **3 worker 容器端到端**：`docker compose up -d --build` → 同一账号连错 6 次密码（HTTP，经 8000 端口，`GUNICORN_WORKERS=3`）→ 第 6 次被拦并出现「尝试次数过多」；同一 SSO Ticket 提交两次 → 第二次出现「Ticket 已使用」。同时给出**反证**：把 `CACHES` 临时改回 LocMem 时同样 6 次不会被拦（证明这一版才修好）。
4. **生产 MySQL 唯一键路径**：在 `constellatio-web-1`（`DB_ENGINE=mysql`）里实测 —— 建表成功、并发 `add` 只一个 `True`、重复 INSERT 的报错类型与 errno（`1062 Duplicate entry`）与 sqlite（`UNIQUE constraint failed`）对比记录。
5. **门禁三条**：`manage.py check` / `ruff check .` / `manage.py test --noinput` 全绿，测试数 352 → 357（只增不减）。

## 八、验收记录（2026-11-10 实测）

### 1. 本地（sqlite）建表 + 连调两次 `add`

```
$ venv\Scripts\python.exe manage.py createcachetable          # 无输出（幂等）
$ sqlite3 schema: CREATE TABLE "constellatio_cache" (
      "cache_key" varchar(255) NOT NULL PRIMARY KEY,
      "value" text NOT NULL, "expires" datetime NOT NULL)
$ manage.py shell -c "cache.add('v173:accept','v'); cache.add('v173:accept','v')"
add#1 = True
add#2 = False
```

### 2. 多进程抢同一键：恰好一个 `True`

sqlite（两个独立 OS 进程，同一目标时刻开抢）：

```
pid=46024 add(v173:race) -> True
pid=10852 add(v173:race) -> False
表内该键行数 = 1
```

MySQL（`docker exec constellatio-web-1`，两个独立进程）：

```
[pid 53] add -> True
[pid 47] add -> False
SELECT COUNT(*) ... LIKE '%v173:race-mysql%'  ->  1
```

### 3. `GUNICORN_WORKERS=3` 容器端到端

容器启动日志（新镜像，`entrypoint.sh` 已插建表步骤；gunicorn 26.2.0 起 3 个 worker，pid 12/13/14）：

```
[entrypoint] migrate
[entrypoint] createcachetable
[entrypoint] collectstatic
```

**(a) 同一账号连错 6 次密码**（HTTP 经 8000 端口，每请求重新取 csrf token，不跟随 302）：

```
== 校准：正确密码 ==            302 登录成功（被重定向）
   第 1 次错密码: 用户名或密码错误
   第 2 次错密码: 用户名或密码错误
   第 3 次错密码: 用户名或密码错误
   第 4 次错密码: 用户名或密码错误
   第 5 次错密码: 用户名或密码错误
   第 6 次错密码: 尝试次数过多（被拦）
== 错满后：再用正确密码 ==      尝试次数过多（被拦）
```

**(b) 同一 SSO Ticket 提交多次**（Ticket 由容器内 `manage.py sso_ticket admin` 签发）：

```
第 1 次提交: 302 登录成功（Ticket 被接受）
第 2 次提交: Ticket 已使用（重放被拒）
第 3 次提交: Ticket 已使用（重放被拒）
```

**(c) 反证（v1.7.2 原状，`CACHES` 回退 LocMem）**：3 个独立进程各连错 2 次（合计 6 次）后，各进程内计数停在 2、均未锁定 —— 即阈值 5 实际要连错 15 次才触发，与 v1.7.2 现象一致：

```
pid=67428 本进程错 2 次 -> counter=2, locked=False（阈值 5）
pid=84904 本进程错 2 次 -> counter=2, locked=False（阈值 5）
pid=63016 本进程错 2 次 -> counter=2, locked=False（阈值 5）
```

### 4. 生产 MySQL 的唯一键冲突路径（真跑）

建表结果（MySQL 8.0，utf8mb4，InnoDB）：

```
CREATE TABLE `constellatio_cache` (
  `cache_key` varchar(255) NOT NULL,
  `value` longtext NOT NULL,
  `expires` datetime(6) NOT NULL,
  PRIMARY KEY (`cache_key`),
  KEY `constellatio_cache_expires` (`expires`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```

同一 `cache_key` 重复 INSERT 的报错类型（两个引擎都落在 `IntegrityError` ⊂ `DatabaseError`，即 `_base_set` 的 `except DatabaseError: return False` 能接住）：

| 引擎 | 第 2 次 INSERT 结果 | `isinstance(DatabaseError)` |
|---|---|---|
| MySQL 8.0 | `IntegrityError: (1062, "Duplicate entry ':1:v173:dup-witness' for key 'constellatio_cache.PRIMARY'")` | `True` |
| sqlite | `IntegrityError: UNIQUE constraint failed: constellatio_cache.cache_key` | `True` |

> 注意日志里的键形态 `:1:v173:dup-witness`：`KEY_PREFIX`（空）+ `VERSION`（1）会拼在键前面，`add()` 与 `set()` 都走同一个 `make_and_validate_key`，所以两者互斥关系成立。

### 5. 门禁三条

```
venv\Scripts\python.exe manage.py check          -> System check identified no issues (0 silenced).
venv\Scripts\ruff.exe check .                    -> All checks passed!
venv\Scripts\python.exe manage.py test --noinput -> Ran 357 tests ... OK
```

> 测试入口说明：本机受限令牌下 `tempfile.mkdtemp()` 建的 0o700 目录不可写，`plugins/approval/tests_v155.py` 的 3 处附件用例会因环境报 `PermissionError`（8 个 error，与本次改动无关）。用 `venv/run_tests_shim.py`（只把 mkdtemp 换成 0o777）跑同一套 357 项：**OK**。测试代码零改动、未新增 skip、未放宽断言。

### 6. 提交与 tag 范围披露

- tag `v1.7.3` → `5342093`（本迭代末提交），工作区与 tag 一致（`git diff v1.7.3` 为空）。
- `git log v1.7.2..v1.7.3` 区间内另含开工前既有提交 `0767f43`（论文演示数据集脚本），**非本迭代产物**；不移动 tag（force push 收益不抵风险）。
- 部署产物与本 tag 内容一致：重建镜像后 `settings.py` / `test_runner.py` / `tests_cache.py` / `entrypoint.sh` / `sso/ticket.py` / `README.md` / 本文件 md5 逐一比对相同。


## 九、不做 / 已知边界

- 不引入 Redis 或任何新依赖；不动 `LOGIN_FAIL_LIMIT` / `LOGIN_FAIL_WINDOW`。
- 不用 `try/except` 兜缓存异常：缺表时登录页/SSO 页会 500（与"静默放行"相比是安全方向），已在 §四 明确。
- 不改 `blockchain` 快照的 `force=True` 语义，只承认它现在跨 worker 生效（行为变化见 §十）。

## 十、待办观察（本版不改，交负责人决定）

1. **限流计数非原子（P2，已排 v1.7.4 第一项）**：`_record_failure()` 是 `get` + `set`，跨 worker 并发会丢更新。实测 3 轮（每轮 6 路并发、全部计错、无一被拦）：最终计数 **2 / 4 / 4**；按串行口径计数应在 **5** 处封顶并拦掉第 6 次，因此单轮突发可多试 2~4 次，慢速爆破不受影响。
   真正原子需要 DB 行锁（`DatabaseCache` 未覆盖 `incr`，继承的 `BaseCache.incr` 是 get + set，且 `set` 不传 timeout 会把窗口重置为默认 TTL，两点都不能解决问题；本项目默认 TTL 为 900s，等于每次自增都把窗口推后 900s，变成滑动窗口）。
   修法（v1.7.4）：`plugins/auth/models.py` 新增独立计数表 `LoginFailureCounter(key UNIQUE, count, window_started_at)`，写走 `transaction.atomic()` + `select_for_update()` + `F('count') + 1`，窗口过期重置 `count=1`，读按 `window_started_at` 判过期，成功登录删行；顺带消除"缓存被 cull 挤掉＝计数凭空消失"的隐患。
   **不能在 `constellatio_cache.value` 上直接 `UPDATE ... value = value + 1`**：该列存的是 `base64(pickle(...))`，SQL 层加 1 会毁数据。
2. **`auth` 锁定检查的失败方向**：`cache.get(...) or 0` 在缺表/DB 故障时抛异常（500），不会把已锁定用户放行；若将来要"缓存挂了就不限制"，需显式设计而不是吞异常。
3. **`blockchain` 校验快照语义变化**：60s 快照从"每进程各一份"变成"全站一份"，`force=True` 手动校验的效果现在对全部 worker 生效（属改善，但行为确实变了）。
4. **缓存表增长**：`DatabaseCache` 只在超 `MAX_ENTRIES` 或过期时清理；`expires` 有索引，`MAX_ENTRIES=10000` 下 500 人规模无压力，规模再上一个量级需重新估算。
5. **Dockerfile 仍以 root 运行**（v1.10 已列，本版不碰）。
