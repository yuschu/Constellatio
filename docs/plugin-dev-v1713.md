# 插件开发文档：v1.7.13 插件开关多 worker 立即可见（删掉进程内缓存）

> 关联：`plugin_host/registry.py`（`_switch_cache` / `PLUGIN_SWITCH_CACHE_TTL` / `PLUGIN_SWITCH_ERROR_TTL` / `invalidate_plugin_switch_cache`）、`plugins/workspace/models.py`（save/delete 失效钩子）
> 版本：v1.7.13 · 文档日期：2026-11-11
> 状态：**✅ 已实现**（440 项测试 + 两 worker 实测与对照实验；见 §六）
> 基线：tag `v1.7.12`（439 项测试）
> 目标：停用/启用插件在**任何 worker 上立即生效**，没有 30 秒窗口

## 一、现状（v1.7.3 引入）

```python
# plugin_host/registry.py
PLUGIN_SWITCH_CACHE_TTL = 30
PLUGIN_SWITCH_ERROR_TTL = 5
_switch_cache = {'expires': 0.0, 'switches': None}

def get_plugin_switches():
    use_cache = not connection.in_atomic_block
    if use_cache:
        cached = _switch_cache['switches']
        if cached is not None and time.monotonic() < _switch_cache['expires']:
            return cached                      # ← 进程内快照
    switches = dict(PluginSwitch.objects.values_list('app_key', 'enabled'))
    ...
```

`PluginSwitch.save()/delete()` 会调 `invalidate_plugin_switch_cache()`。**但这只清「当前进程」的缓存**：

| 场景 | 结果 |
|---|---|
| 单 worker | 停用后立即生效（测试就是这个场景，所以一直绿） |
| **3 worker** | worker A 处理写操作并清自己的缓存；worker B/C 的快照还在 → **最多 30 秒内仍按旧值放行** |

后果不是「界面晚 30 秒变」这么轻：`PluginRouteGuardMiddleware` 用它决定**是否拦截路由**，
所以「已停用的插件在部分 worker 上仍可访问」——这正是 v1.7.9 ~ v1.7.11 花三版消灭的「越权语义不一致」的另一种形态。

## 二、方案：直接删掉进程内缓存

```python
def get_plugin_switches():
    """插件 DB 开关快照 {app_key: enabled}。

    每次调用都读表（v1.7.13 删掉了 v1.7.3 引入的进程内 TTL 缓存：多 worker 下
    写进程只能清自己的缓存，其它 worker 会继续用旧快照，导致「已停用的插件仍可访问」）。
    表很小（插件数 × 环境，个位数到十几行）。实测每请求查开关表：**普通页面 4 次、首页 6 次**（`PluginRouteGuardMiddleware` 1 + `context_processors` 1 + `charts.chart_switch_enabled` 2；首页另有 `views:get_enabled_plugins` / `views:plugin_counts` / `workbench` 各 1），成本可忽略。
    """
    try:
        from plugins.workspace.models import PluginSwitch
        return dict(PluginSwitch.objects.values_list('app_key', 'enabled'))
    except (ImportError, LookupError, OperationalError, ProgrammingError):
        logger.warning('插件开关表不可用，回退静态 OA_PLUGINS 配置', exc_info=True)
        return {}
```

一并删掉：

| 删除项 | 原因 |
|---|---|
| `_switch_cache` | 就是缺陷本身 |
| `PLUGIN_SWITCH_CACHE_TTL` | 缓存没了，配置是死配置 |
| `PLUGIN_SWITCH_ERROR_TTL` | 同上；它是「表不可读时 5 秒内不再打 DB」的降级缓存 |
| `invalidate_plugin_switch_cache()` | 没有进程内状态可失效；调用方一并清理 |
| `use_cache = not connection.in_atomic_block` 分支 | 它是缓存逻辑的总开关；缓存没了它只剩一个无用变量，`connection` 的 import 也随之删掉 |
| `tests_registry.py` 的 `mock.patch.object(connection, 'in_atomic_block', False)` | 那个 patch 存在的唯一目的就是让缓存路径生效 |
| `workspace.PluginSwitch.save()` 里的失效调用 | 同上（`delete()` 与 `post_delete` receiver 同样处理） |

> **降级行为的代价**：表不可读（首次 `migrate` 之前 / workspace 被停用）时，每个请求会打一次失败的
> SELECT 并记一条 warning。这是「已损坏状态」下的噪声，可接受；若将来觉得吵，正确做法是启动期检查并
> 明确报错，而不是再造一个进程内状态把延迟问题藏回来。
>
> **每请求查询次数**：实测调用点是 `context_processors`（1 次）+ `PluginRouteGuardMiddleware`（1 次），
> `build_menus(plugins=...)` 支持传入已解析结果、不会重复查。合计 2 次 `SELECT app_key, enabled`。

## 三、为什么**不**用另外两种方案（留在文档里，供后来人参考）

### 3.1 信号驱动（否决）

`post_save` 只在**写操作发生的那一个进程**里触发。worker A 停用插件 → signal 在 A 里执行 →
A 清掉自己的缓存；**worker B/C 收不到这个信号**，缓存照旧。结果：

- 单 worker：立即生效（测试绿）；
- 多 worker：仍延迟 30 秒 —— **看起来修了，实际没修**。

这比现状更糟：现状是一个「已知延迟」，信号方案会把它伪装成「已修复」，而验收如果只跑单进程一定会通过。

### 3.2 版本号驱动（否决）

需要一个所有 worker 共享的存储（DB 行或 `DatabaseCache`），每次请求读一次版本号 = 一次查询，
命中变化后再查开关表 = 第二次查询。成本与「直接查表」相同甚至更高，却多一层间接和一份状态。

## 四、实现清单

| 文件 | 改动 |
|---|---|
| `plugin_host/registry.py` | 删缓存三兄弟与 `invalidate_plugin_switch_cache`；`get_plugin_switches` 每次读表 |
| `plugins/workspace/models.py` | 删 `save()` 里的失效调用、`delete()` 覆写、`post_delete` receiver 与 import |
| `plugin_host/tests_registry.py` | `test_ttl_cache_reuses_snapshot_until_invalidated` → 改为「每次调用都读表」用例；`invalidate_plugin_switch_cache` 的 import/setUp 调用清理；错误降级用例保留并改断言 |
| `plugins/workspace/tests*.py`（如有引用） | 同步 |

## 五、测试计划（439 → 440）

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_switch_change_visible_without_invalidation_hook`（替换原 TTL 用例） | 第一次读到 `enabled=True`；**绕过 save 钩子**直接 `PluginSwitch.objects.filter(...).update(enabled=False)`；再调用 `get_plugin_switches()` → 立刻看到 False。用 `.update()` 是关键：它不触发 `save()`，能证明「读到新值」不是因为失效钩子。 |
| 2 | `test_switch_table_error_degrades_to_static`（保留，改断言） | 表不可读时返回 `{}` 且回退静态配置；不再断言缓存行为 |
| 1（新增，替换 TTL 用例） | `test_switch_change_visible_without_invalidation_hook` | `hasattr(registry, '_switch_cache')` / `PLUGIN_SWITCH_CACHE_TTL` / `invalidate_plugin_switch_cache` 均为 False（防回退） |

## 六、验收（**必须两 worker**）

1. 容器以 `GUNICORN_WORKERS=3` 起；
2. 记录 worker 进程 pid：`docker exec constellatio-web-1 ps -o pid,cmd -C gunicorn`；
3. 打开**临时** access log（容器内 env 覆盖，不改仓库）让每条请求带 pid：
   `--access-logfile - --access-logformat '%(p)s %(m)s %(U)s'`；
4. **在容器内**停用插件（必须用容器那套配置改库，宿主机 `python manage.py` 可能连的是另一个库，那样这一步就落空了）：

   ```bash
   docker exec constellatio-web-1 python manage.py plugin_switch off notice
   ```

   随后立刻连打 6 次目标路由；
5. 通过 access log 确认这 6 次**确实落在至少两个不同 pid** 上；
6. **判据**：所有请求都 403/404（按停用语义），**不存在**任何一次「停用前行为」；
7. 对照：在删缓存之前的代码上重复一次，必须能看到至少一次旧行为（证明这个验收真能抓到缺陷）。

> 单 worker 测不出这类缺陷（v1.7.7 的教训）；只测一次请求也可能恰好落在 A 上。

### 六.1 实测记录（2026-11-11 11:50 +08:00）

探针容器：`constellatio-web:latest`（新代码）3 worker、`--access-logformat '%(p)s %(s)s %(U)s'`，端口 8010；
停用动作在部署容器内执行（`plugin_switch off notice`），改的是同一个 MySQL 库。

| 版本 | 停用前 | 停用后立刻 6 次 | 命中 worker |
|---|---|---|---|
| **新代码（删缓存）** | `/plugins/notice/` 200 | **6 次全部 404「插件已停用」** | pid `<8>`、`<9>`（≥2 个） |
| **旧代码（v1.7.12，缓存仍在）** | 200 | **6 次全部 200（旧快照放行）** | pid `<8>`、`<9>`、`<10>` |

> 这就是那条判据的意义——**如果验收对「有缺陷的代码」也通过，它就什么也没验**。
> 旧代码在完全相同的操作序列下 6/6 放行，新代码 6/6 拦截，差异只能来自「删掉进程内缓存」。
>
> 口径说明：本实验的停用动作来自**另一个进程**（部署容器的 `manage.py`），所以旧代码里 3 个 worker
> 的缓存全都没被清；生产中从 Web UI 停用时，处理写操作的那个 worker 会清自己的缓存、其余仍保留旧快照，
> 表现为「部分 worker 放行」。两种形态都是同一个缺陷，本实验取更彻底的一种。
> 实验后已恢复 `notice` 为启用，探针容器与对照镜像均已删除。

## 七、不做 / 已知边界

- 不做「停用插件时清 DB 会话」之类的级联动作（与本缺陷无关）。
- 不引入共享缓存层（DatabaseCache）来存开关快照：查询成本已足够低，多一层反而增加失效面。
- **不合并同一请求内的重复查询**（middleware 结果挂到 `request` 供 context processor 复用、
  `views:84` 与 `views:117` 合并）：本版单一主题是「删掉一个缺陷」，掺优化会让回溯变难，记入 roadmap 待办。
- 表不可读时的降级仍然是「回退静态配置」，与现状一致。

## 八、待办（跨版本，勿丢）

1. **真机上做一次浏览器冒烟**（v1.7.12 遗留）：打开列表页确认 401 真的跳登录、CSP 未拦截。
   桩 DOM 替代的是「每次改都点一遍」，不是「上线前从不点」。
2. `user` 插件对象级校验扫尾（`get_object_or_404` 系列，语义多为「不存在」，收益低）。
3. v1.8 模板引擎插件化（Jinja2 Provider）。
