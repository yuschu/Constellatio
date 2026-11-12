# Constellatio Release Notes

> 本文件是**发版总入口**：每一版做了什么、怎么升级、按 tag 检出时要注意什么。
> 单版实现细节仍以 `docs/plugin-dev-vXXXX.md` 为准，本文件只做汇总与指路。

---

## 一、v1.7.x 收口发版（2026-11-12）

| 项 | 值 |
|---|---|
| 发版基线 | tag `v1.7.14` —— 即**本文档所在提交**（`git rev-parse 'v1.7.14^{}'` 可解引用） |
| 测试基线 | **467 项全绿**（`manage.py check` / `ruff check .` / 全量测试三项门禁） |
| 验收补充 | 真机浏览器三态验收已完成（2026-11-12 09:41–09:45 (+08:00)，见 `docs/plugin-dev-v1712.md` §5.2） |
| 结论 | **v1.7.x 功能线到此收口**（不再往功能线叠版本）；后续**加固包与修补另立版本**，架构级变更（模板引擎插件化）走 v1.8 |

### 这个基线上线前请确认

1. `python manage.py createcachetable` 已执行（v1.7.3 起缓存走 `DatabaseCache`，缺表登录直接 500）。
2. 迁移全部应用；审计字段迁移会给**历史行**写 `NULL`（不是伪造时间），不要为"好看"去掉末尾那条 `RunSQL` 回 NULL 的语句。
3. 容器日志只走 console（`DJANGO_LOG_TO_FILE` 默认 0，多 worker 不轮转同一文件）。
4. 插件被停用到"无 UI 可进"时，用 `python manage.py plugin_switch on <key>` 兜底。

### 1.1 v1.7.16（2026-11-12，CSP 加固）

tag `v1.7.16`（annotated）。基线 472 → **482 项全绿**（新增 10 条 CSP 用例）。

- 中间件 `plugin_host/csp.py`：每请求一个 nonce（`request.csp_nonce`），响应头下发 10 条指令；
  位置在 `SecurityMiddleware` 之后，400/403 也带头；硬 500 由 `handler500` 补头；
- `script-src 'self' 'nonce-…'`（**不给 `'unsafe-inline'`**）：13 处内联 `<script>` 加 nonce；
- `style-src 'self' 'unsafe-inline'`：全站 137+ 处 `style=` 属性，收紧会让图表高度塌成 0；
- 6 处 `onclick="return confirm('…')"` → `data-confirm` + 外部 `static/js/confirm.js`
  （nonce 救不了内联事件，这是把 `script-src` 保住的前提）；
- `/admin/` 不豁免（admin 模板实测内联 0 / `onclick` 0 / `style=` 0）；
- `'unsafe-eval'` 不加：ECharts 的 `new Function` 只在 `JSON.parse` 不可用时触发，理论不触发；
  **真机未验证**，若报 `unsafe-eval` 先上报、不自行加指令。

### 1.2 v1.7.15（2026-11-12，私有化部署收口）

tag `v1.7.15` → commit `39baf42`（annotated）。基线 467 → **472 项全绿**，覆盖率 **96%**（8020 statements / 292 missed），CI 门槛 94。

| 项 | 结果 |
|---|---|
| Bootstrap 离线化 | 两主题 6 处 CDN 引用清零（CSS **和** JS 都本地化）；本地副本 232 803 / 80 721 B，与 CDN 原件字节数一致；靠 `AppDirectoriesFinder` 收集，未新增 `STATICFILES_DIRS` |
| 生产缺 `SECRET_KEY` 拒绝启动 | `DJANGO_DEBUG=0` 且无 key → `ImproperlyConfigured`；开发模式默认 `'1'` 不动 |
| 登出改 POST | GET → 405 且会话仍有效；POST → 302 且 session 失效；两主题改成带 CSRF 的 form（此前全仓对登出零覆盖） |
| compose 层 `SECRET_KEY` 缺省即报错 | 见下——发布前拦下的 P1 |

**发布前拦下的 P1**：`docker-compose.yml` 原写 `${SECRET_KEY:-django-insecure-compose-default-change-me}`，会让上面那条硬要求在 compose 部署下**永不触发**，而那个默认值公开在仓库里——能签出任何 session。已改为 `${SECRET_KEY:?...}`，无 key 时 `docker compose config` / `up` 均 exit=1。

> `check --deploy` 覆盖不到这一条（compose 的 env 不参与 Django system check），所以"零告警"在这一项上会带来假安全感。

真机冒烟（2026-11-12，维护者在真实浏览器执行）：**已通过**。

---

## 二、按 tag 检出时请先读这一节

**原则：已发布的 tag 不回改。** 文档若有遗漏，一律按 `main` 上的路径指路，不用 tag 里的旧版。

下表是逐 tag 的实测结果（`git rev-parse '<tag>^{}'` + `merge-base --is-ancestor`）：

| tag | 指向 | 是否等同"该版最终状态" | 说明 |
|---|---|---|---|
| `v1.7.2` | `503e072` | ✅ | 文档提交即当版末提交 |
| `v1.7.3` | `5342093` | ⚠️ **文档不完整** | **不含** `b04f512`（当版文档纠偏：缺表后果、缓存对照方法、版本号等口径修正）。要读完整版 → `main` 的 `docs/plugin-dev-v173.md` |
| `v1.7.4` | `e07bec6` | ⚠️ **文档不完整** | **不含** `514b90c` / `c552314`（收尾的措辞与断言说明修正）。要读完整版 → `main` 的 `docs/plugin-dev-v174.md` |
| `v1.7.5` | `1d0c317` | ✅ | — |
| `v1.7.6` | `7d509e2` | ✅（**经重建**） | 原 tag 因 `git add` 整条失败漏了分页三文件，检出不可运行；已拆提交重建。**任何早于重建的 `v1.7.6` 引用都不可用** |
| `v1.7.7` | `626d6c0` | ✅ | — |
| `v1.7.8` | `455628c` | ✅（**经重指**） | 纳入 `update_fields` 部分更新丢审计列的收尾修复 |
| `v1.7.9` | `681e405` | ✅（**经移动**） | 纳入时间依赖用例修复（否则 tag 声称 420 绿却缺修复） |
| `v1.7.10` | `b41a813` | ✅ | — |
| `v1.7.11` | `36b4f12` | ✅ | — |
| `v1.7.12` | `8e9294d` | ✅ | — |
| `v1.7.13` | `ba73e35` | ✅ | — |
| `v1.7.14` | 本文档所在提交 | ✅ | 经三次移动：纳入收尾两处修复、真机冒烟记录、本文档。**自此冻结，不再移动** |

两个历史 tag（`v1.7.3`、`v1.7.4`）**不会被后移**：后移只会让"发布快照"与"实际提交"再对不上一次，收益仅是检出时多两份文档。按上表指路即可。

---

## 三、升级须知：v1.7.x 的行为变更

只列**调用方可观察**的变更，其余都是内部重构或文档修正。

| 变更 | 版本 | 变更前 → 变更后 | 谁需要关心 |
|---|---|---|---|
| 登录失败限流语义 | v1.7.7 | "允许 5 次失败" → "**第 5 次失败当次即锁**"（`LOGIN_FAIL_LIMIT=5`） | 运维 / 用户支持话术 |
| 已登录但无权限 | v1.7.9 | 302 回工作台 → **403**（403 页固定文案 + 返回工作台 / 上一页两按钮） | 前端调用方、脚本 |
| 审批对象级越权 | v1.7.10 | 302 / 404 → **403**；`approval_hide` 的 404 → 403；`services` 抛的 `PermissionError` 不再被静默吞 | 任何按状态码分支的调用方 |
| 匿名访问 JSON 接口 | v1.7.11 | 302 → **401** `{"code":"authentication_required"}`；普通页面请求仍 302 到登录页 | API 调用方、前端 fetch |
| 前端图表失败反馈 | v1.7.12 | 四种失败同色（"图表不可用"）→ 三态：401 跳登录带 `next`、403"无权查看该数据"、其它"数据暂时不可用" | 用户可见 |
| 插件停用生效时间 | v1.7.13 | 多 worker 下"最多 30 秒" → **即时**（删掉进程内缓存）；开关表不可读时每请求一条 warning | 运维（停用插件后不再有窗口期） |
| `user_status` 未知 action | v1.7.14 | 静默 redirect → **500 `ValueError`** | 见下 |
| 登出端点 | v1.7.15 | `GET /plugins/auth/logout/` 200 → **405**（会话保持不变）；必须改成 POST + CSRF | 前端、脚本、书签、任何外链 |
| 部署启动 | v1.7.15 | 生产模式（`DJANGO_DEBUG=0`）缺 `SECRET_KEY` → 拒绝启动；`docker compose` 缺 key 时 `config` 与 `up` 均 exit=1 | 运维（部署脚本/CI 必须注入 key） |

关于最后一条：调用方传了四个合法值之外的东西，属于**程序错误**，所以没有为了页面好看改回静默，也没有顺手改成 400（那会让程序错误看起来像正常业务校验失败）。要变成 400 应走 `BusinessError` 通道，已在 `docs/plugin-dev-v1714.md` §4.6 写明。

同一版新增的一条**留痕**：补卡登记会记 `logger.info('补卡登记 operator=… target=… date=… status=…')`。审计列（`created_by`/`updated_by`）记的是"这一行被谁写过"，日志记的是"谁发起了这次补卡"，两者不可相互替代。

---

## 四、测试基线演进（只增不减、无 skip）

| 版本 | 用例数 | 版本 | 用例数 |
|---|---|---|---|
| v1.7.0 | 259 | v1.7.8 | 413 |
| v1.7.1 | 323 | v1.7.9 | 420 |
| v1.7.2 | 352 | v1.7.10 | 427 |
| v1.7.3 | 357 | v1.7.11 | 434 |
| v1.7.4 | 368 | v1.7.12 | 439 |
| v1.7.5 | 380 | v1.7.13 | 440 |
| v1.7.6 | 387 | v1.7.14 | 467 |
| v1.7.7 | 403 | v1.7.15 | 472 |
| | | v1.7.16 | **482** |

v1.7.8 交付时为 410，收尾补到 413；v1.7.14 交付时 466，收尾补到 467。数字增长来自新增用例，没有放宽任何既有断言。

---

## 五、已知遗留（不在本发版范围）

| 项 | 性质 |
|---|---|
| 登录失败计数表的孤儿行无定期清理 | 运维成本，非缺陷 |
| `bulk_create` / `QuerySet.update()` 不填审计人（公告批量已读走这条） | 仅文档记录 |
| 403 / 401 页没有"申请权限 / 重新登录"入口 | 小改动，需产品定文案 |
| `user` 插件的 `get_object_or_404` 系列未做对象级扫尾 | 收益低（多为管理员查询） |
| 同一请求内多次查插件开关表（首页 6 次、插件页 3~4 次） | 纯成本优化，`docs/roadmap.md` 待办 |

---

## 六、文档地图

- 发版与升级 → 本文件
- 迭代路线与差距矩阵 → `docs/roadmap.md`
- 硬约束与验收标准 → `docs/constraints-and-acceptance.md`
- 单版实现细节 → `docs/plugin-dev-vXXXX.md`（索引见 README「文档索引」）
- 真机冒烟记录 → `docs/plugin-dev-v1712.md` §5.2

---

## 七、下一步计划（v1.7.x 之后）

收口不等于"没有后续工作"，只是**不再往功能线上叠版本**。下一阶段是两条线：

### 7.1 加固包（v1.7.15 已落地三项，见 `docs/plugin-dev-v1715.md`）

**已完成**（实测证据在 `docs/plugin-dev-v1715.md`）：

| 项 | 结果 |
|---|---|
| Bootstrap 离线化 | 两个主题 6 处 CDN 引用清零（CSS **和** JS 都本地化——只做 CSS 会让断网时下拉/折叠全废，而"样式完整"这个验收词恰好会把该问题掩盖）；本地副本 232 803 / 80 721 字节，与 CDN 原件一致；`AppDirectoriesFinder` 自动收集，未新增 `STATICFILES_DIRS` |
| 登出改 POST | GET → 405 且会话仍有效、POST → 302 且 session 失效；两主题改成带 CSRF 的 form。全仓此前对登出**零覆盖**，本次补 2 条 |
| 生产缺 `SECRET_KEY` 拒绝启动 | `DJANGO_DEBUG=0` 且无 `SECRET_KEY` → `ImproperlyConfigured`（附生成命令）；开发模式默认 `'1'` 不受影响 |

**覆盖率门槛 94 不属于加固包**：它是工程门槛（当前 96%，门槛取当前 − 2），与安全加固是两件事，v1.7.15 一并落地只是排期合并。

**剩余未收口项**：

| 项 | 现状（2026-11-12 实测） | 处置 |
|---|---|---|
| CSP（`Content-Security-Policy`） | **已收口**（v1.7.16）：10 条指令、`script-src` 严格（nonce，无 `'unsafe-inline'`）、`style-src 'unsafe-inline'`（137+ 处 `style=` 属性，收紧会崩排版与图表高度）；13 处内联脚本加 nonce、6 处 `onclick` 改 `data-confirm`；`/admin/` 不豁免（实测 0/0/0） | 详见 `docs/plugin-dev-v1716.md`；真机「控制台零 CSP 报错」待评审者执行 |
| `docker-compose.yml` 的 `SECRET_KEY` 默认值 | **已收口**（`39baf42`）：原写 `${SECRET_KEY:-django-insecure-compose-default-change-me}`，让 7.2 的硬要求在 compose 部署下永不触发，而默认值公开在仓库里 | 已改 `${SECRET_KEY:?...}`；实测无 key 时 `docker compose config` 报 `required variable SECRET_KEY is missing a value`（exit=1），带 key 解析通过 |

验收口径：离线化后断网加载走一遍全站；登出改 POST 后 GET 必须 405；生产模式缺 key 必须拒绝启动；`check --deploy` 零告警的前提是 `DJANGO_DEBUG=0` + 真随机 50 位 key + `DJANGO_HTTPS=1` + `DJANGO_SSL_REDIRECT=1`（默认 HTTP 配置下 W004/W008/W012/W016 四条告警是设计预期，不是故障）。

### 7.2 v1.8 模板引擎插件化

Jinja2 Provider 与 Django 模板并存，属架构级改动，**单独起线**，不与加固包混版。

### 7.3 排在后面的小项

403 / 401 页加「申请权限 / 重新登录」入口；`user` 插件 `get_object_or_404` 系列的对象级扫尾；同一请求内的开关表查询合并（首页 6 次、插件页 3~4 次）。三项均在 `docs/roadmap.md` 待办，按优先级择机。
