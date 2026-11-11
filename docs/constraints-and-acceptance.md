# 约束与验收规范

> 项目：《基于 Django 的企业办公自动化系统的设计与实现》
> 设计思想：万物皆可插件（全栈插件化）
> 文档版本：v1.9 · 2026-10-22（v1.5 主题插件化：Corporate Clean 默认 + Risograph 备选）
> 适用范围：本项目全部设计、开发、测试、文档活动

---

## 一、技术栈约束（已定版，不得擅自更改）

- 语言：**Python 3.13**
- 框架：**Django 5.2 LTS**（插件容器）
- 数据库：**MySQL 8.0**（默认）；可通过配置切换 sqlite/postgres（演示用途）
- 前端：**Django 模板 + Corporate Clean 企业简洁风（默认）/ Risograph（备选）**；**禁止引入 Vue/React 等前端框架**
- 图表：**ECharts 5**（统计看板）
- 服务器：Gunicorn + WhiteNoise（静态直托，免 Nginx）
- 部署：Docker Compose（`docker compose up -d`），**Windows / macOS / Linux 多平台通用**

## 二、架构约束（万物皆可插件）

1. **容器唯一固定**：plugin_host（插件注册表/自动发现/统一外壳/信号总线/配置中心）是系统唯一不可替换核心
2. **业务全插件化**：auth、user、approval、notice、attendance、blockchain 全部为插件，无"不可拔业务模块"
3. **基础设施可插拔**：数据库后端、模板引擎、主题 UI、图表引擎、认证后端均通过 Django 官方机制可切换
4. **插件契约强制**：每个插件必须实现 PluginMeta（name/version/menus/permissions/urls/signals/templates/models），缺一不可
5. **插件间解耦**：跨插件通信只走 signals，**禁止插件间直接 import 对方 models/views**
6. **注册驱动**：插件启停只通过 `OA_PLUGINS` 配置，删一行即停用，导航/权限/路由自动收敛

## 三、功能边界

### 必做（5 个业务插件 + 容器）

| 插件 | 功能范围 |
|---|---|
| auth | 登录/登出、会话管理、密码修改 |
| user | 部门管理、用户管理、角色管理、RBAC 权限分配 |
| approval | 请假/报销/用章三类审批、状态机流转、审批记录留痕、我的申请/我的待办 |
| notice | 公告发布、置顶、已读标记、公告列表/详情 |
| attendance | 上下班打卡、打卡记录、月度统计（ECharts 看板） |
| blockchain | 操作留痕上链（订阅全局信号写入哈希链）、链完整性校验、留痕查询 |

### 必不做（超出当前版本范围，列入 Roadmap）

- 多维表格 / 低代码搭建（超规模）
- ERP / CRM 集成（超规模）
- 公文电子签章 / 套红（政务级，超规模）
- AI 工作流 / 智能审批
- 微服务化、单元化架构（规模不需要）

## 四、规模约束

- 目标规模：≤ 500 人、单服务器部署
- 数据规模：核心表 10 张以内
- 并发目标：满足中小团队日常使用场景即可，不做高并发优化（Roadmap 中说明取舍）

## 五、验收标准

### 功能验收
- [ ] 6 个插件（auth/user/approval/notice/attendance/blockchain）全部可用，CRUD 完整
- [ ] 审批流：发起→审批→通过/驳回→归档→留痕可查，状态机正确
- [ ] 公告：发布/置顶/已读统计正确
- [ ] 考勤：打卡去重、月度统计与 ECharts 看板数据一致
- [ ] RBAC：不同角色登录看到不同菜单/操作，越权访问被拦截
- [ ] 区块链留痕：审批/公告/考勤关键操作自动上链；手动篡改一条链记录 → 完整性校验报警

### 架构验收（演示项）
- [ ] 从 `OA_PLUGINS` 停用 approval → 导航消失、系统照常运行
- [ ] `DATABASES` 由 MySQL 切 sqlite → 重启即跑（演示数据库可插拔）
- [ ] 新增一个最小插件（会议室示例）→ 注册一行 → 系统自动出现菜单并可访问
- [ ] 主题切换（Bootstrap → 自定义）不破坏功能

### 部署验收
- [ ] 每版 Docker Compose 重新构建并部署成功，负责人可从 http://localhost:8000 访问测试

### 文档验收
- [ ] 需求规格说明书
- [ ] 数据库设计文档
- [ ] 测试报告（功能测试 + 部分单元测试）
- [ ] 部署文档 + 演示脚本

## 五点四、git push 失败必须分类诊断（v1.7.9 收尾）

同一个「push 失败」出现过三种完全不同的病因，**不要默认是凭据**：

| 症状 | 病因 | 处置 |
|---|---|---|
| `could not read Username` / `failed to execute prompt script` | 凭据（helper 失效或 `GIT_TERMINAL_PROMPT=0`） | 修 credential helper / 交互推送 |
| `HTTP 408` + `send-pack: unexpected disconnect` | 大 pack / 网络超时 | `http.version=HTTP/1.1` + 加大 `http.postBuffer` |
| `schannel: failed to receive handshake, SSL/TLS connection failed` | **TLS 后端与代理不兼容**（Windows schannel 走代理握手失败） | `git config http.sslBackend openssl` |
| `TcpTestSucceeded=False` | 网络真不通 | 查网络/代理，别改 git |

> 本项目仓库级已固化为 `http.sslBackend = openssl`（代理环境）。回退用 `git config http.sslBackend schannel`。
> 教训：把每次失败都标成「凭据阻断」比故障本身更容易误导排查——先看报错原文再下结论。

## 五点六、前端错误处理的硬约束（v1.7.12 起）

1. **401 跳转的 `next` 只能是页面 URL**：`location.pathname + location.search`。
   禁止拼接接口地址（`el.dataset.statsUrl`、`/plugins/…/stats/` 之类）——那会让用户登录后被扔到一坨 JSON 上。
   这个错误在「想保留筛选条件」时极易犯，因为 statsUrl 里正好也有 `?days=`。
2. **被 `{% include %}` 的模板必须自带 `{% load … %}`**：include 独立编译，父模板的 `{% load %}` 不继承；
   缺 `{% load i18n %}` 只会在运行时 `TemplateSyntaxError`，两个页面直接 500。
3. **哨兵值要写进注释**：用 `null` 表示「已被错误处理函数消费」时，必须注明「该接口永远返回对象」，
   否则将来某个接口合法返回 `null` 会被静默跳过、界面空白且无提示。
4. **错误处理函数不得抛异常**：`showEmpty` 一类兜底渲染若抛错，会落进 `.catch` 被统一覆盖成「不可用」，
   正好抹掉 401/403 的区分。

## 五点五、迁移与 DDL 硬约束（v1.7.8 起）

1. **禁止对 `migrations/` 使用任何编号 glob**（`0002*`、`00*_*.py` 等）。迁移文件名由 Django 按内容生成、
   不可预测；按编号猜会命中历史迁移，把 `RunSQL` 一类语句写进早已应用的旧迁移 —— 在**新装库**上执行一条
   永远不该执行的 DML，且**在已有库上不会暴露**，属于最难查的一类事故。
   正确做法：从 `makemigrations` 输出里复制完整文件名，或取 `git status` 该目录下新增的 `??` 项。
2. **迁移 SQL 合格判据**：`sqlmigrate <app> <migration>` 里每一条非空 SQL 都必须能被解释，且落在
   「新增列 / 新增索引 / **放宽** NULL」三类之内。
3. **硬红线**：出现 `MODIFY ... NOT NULL`（收窄可空性）立刻停止 —— 历史 NULL 行会在下次写入时失败。
4. 新增 `auto_now` / `auto_now_add` 列时注意：`SchemaEditor._effective_default()` 会给这类列注入
   `timezone.now()`（`django/db/backends/base/schema.py:474`，`null=True` 时同样命中），历史行会被刷成
   迁移执行时间。若历史行必须保持 NULL，迁移末尾要显式 `RunSQL ... SET <col> = NULL`。
5. **报告里的迁移操作计数**（AddField / AlterField / RunSQL 条数）不得手数，用正则统计后粘贴。

## 六、开发规范

- **Python**：PEP 8，代码注释中文，函数/类有 docstring
- **Django**：MVT 分层，业务逻辑放 views/services，禁止在模板里写复杂逻辑
- **数据库**：模型迁移用 `makemigrations`/`migrate` 管理，禁止手改表
- **命名**：插件目录小写（auth/user/approval/notice/attendance/blockchain），类名驼峰，URL 前缀 `/plugins/<name>/`
- **Git**：提交信息格式 `类型(范围): 描述`（feat/fix/docs/refactor），每功能一个提交
- **测试**：核心逻辑（审批状态机、RBAC）至少写单元测试

## 七、风险与缓解

| 风险 | 缓解措施 |
|---|---|
| 插件间数据依赖（审批引用用户） | 只通过 user 插件暴露的 API/信号取数，不直接 import |
| 信号死循环（互相触发） | 信号处理函数幂等、加去重标记 |
| 权限冲突（多插件贡献权限码重名） | 权限码强制 `插件名_权限` 前缀，注册时校验冲突 |
| 插件停用后残留数据/路由 404 | 注册表统一收敛路由与导航；停用仅隐藏不删数据 |
| 范围蔓延（想加功能） | 对照"必不做"清单，超规模功能一律移入 Roadmap / 后续版本 |

## 八、里程碑（8 周）

| 周次 | 交付物 | 验收门 |
|---|---|---|
| 1-2 | 需求分析 + 架构设计 | 设计评审通过 |
| 3-4 | 容器 + auth/user 插件 | RBAC 可用 |
| 5 | approval 插件 | 审批闭环跑通 |
| 6 | notice 插件 | 公告已读闭环跑通 |
| 7 | attendance 插件 + 看板 | 统计正确 |
| 8 | blockchain 插件 + 链校验 | 篡改检测报警 |
| 9 | 整合联调 + 测试 + Docker + 发布 | 三项验收全过 |

**当前进度**：✅ v0.1~v0.6（容器/RBAC/审批/公告/考勤/留痕）；✅ v1.0 整合部署；✅ v1.1 workspace 运行时插件启停；✅ v1.2 user 增强 + approval 会签；✅ v1.3 structure 职能制架构模板；✅ v1.4 language 中英切换；✅ v1.5 主题插件化（Corporate Clean 默认 + Risograph 备选 + 登录占位入口 + 首屏 loader）；✅ v1.5.1 全站文案补全 + 留痕详情；✅ v1.5.2 留痕插件/动作名本地化；✅ v1.5.3 个人中心 / 权限范围 / 登录回填 / 公告可见；✅ v1.5.4 权限等级 L0–L3 / 全员基线 / 角色模板权限 / 插件准入 / 管理岗签到详情；✅ v1.5.5 审批动态表单 / 抄送 / 签到筛选与补卡 / 工作台双视图 / 菜单高亮 / 密码权限；✅ v1.5.6–v1.5.18 组织结构 / 审批路由 / 重申请 / 抄送直系领导（184 项测试）；✅ v1.6 图表插件化 + ECharts 月度看板 / 停用表降级；✅ v1.6.1 图表运行时开关 + 留痕链统计看板；✅ v1.6.2 工作台图表化大盘；✅ v1.6.3 Banner 白字 + 侧栏吸顶；✅ v1.6.4 顶部导航吸顶并部署；✅ v1.6.5 指标卡按钮底部居中 + 基线对齐并部署；✅ v1.6.6 插件分布卡片紧凑化并部署；✅ v1.6.7 指标卡按钮统一去箭头并部署；✅ v1.6.8 部门明细表格拆分并部署；✅ v1.6.9 图表双卡等宽等高并部署；✅ v1.6.10 公告简报卡片化 + 列表/详情合并（237 项测试）并部署；✅ v1.6.11 部门管理页排版优化并部署；✅ v1.6.12 角色 / 审批 / 待办三页统一排版并部署；✅ v1.6.18 今日状态卡片压缩并等高；✅ v1.6.19 部门操作按钮配色调整；✅ v1.6.20 部门状态徽标绿色 + 防折行 —— 2026-10-24；**已交付 tag v1.6.20（237 项测试全绿）**；✅ v1.7.0 企业 SSO（HMAC Ticket）+ 消息提醒站内信（259 项测试全绿）并部署——2026-10-24；✅ v1.7.1 安全与并发修复包：审批/留痕/打卡行锁与事务、审批对象级鉴权、编辑页不得改启用状态、插件开关仅 POST、传输安全开关、登录限流与密码校验器、注册表系统检查、开关缓存、菜单权限集合、列表分页、留痕校验快照、ruff + GitHub Actions 门禁（323 项测试全绿）并部署——2026-10-27，**已交付 tag v1.7.1**；✅ v1.7.2 公告极简化（单列公告流 / 标题与正文同屏 / 进入即已读 / 已读明细下沉管理岗页）+ 考勤规则（`AttendanceRule` 单例、设置页、`attendance_rule_manage` 权限、看板口径展示）（352 项测试全绿）并部署——2026-10-27，**已交付 tag v1.7.2**；✅ v1.7.3 共享缓存：`CACHES` 换 `DatabaseCache`（登录失败限流 / SSO 防重放跨 gunicorn worker 成立，零新依赖）、`entrypoint.sh` 建表、`TEST_RUNNER` 为测试库建表（357 项测试全绿）并部署——2026-11-10，**已交付 tag v1.7.3**；✅ v1.7.4 登录守卫中间件化：`LoginRequiredMiddleware` 默认拦截 + 6 个 `@login_not_required` 白名单（登录 / 退出 / 忘记密码 / 语言切换 / SSO 两入口），两条集合护栏钉住匿名可达面，admin 行为断言（368 项测试全绿）并部署——2026-11-10，**已交付 tag v1.7.4**；✅ v1.7.5 错误页 + 日志与异常分类：`templates/400|403|404|500.html`（500 独立渲染、不依赖上下文）、`LOGGING`（容器只走 console，`DJANGO_LOG_TO_FILE` 默认 0）+ `RequestIdMiddleware`（`X-Request-Id` + 日志 filter）、`BusinessError`→400 / `ObjectPermissionDenied`→403 / `ExceptionGuardMiddleware` 兜底、JSON 错误体统一 `{code,message}`（380 项测试全绿）并部署——2026-11-10，**已交付 tag v1.7.5**；✅ v1.7.6 列表分页统一 + 公告增量已读 + 留痕翻页：`plugin_host/pagination.py` 唯一入口、`templates/includes/pagination.html` 公共分页块（`{% querystring %}` 保住筛选参数）、user/notice 接分页、公告只登记当页未读、留痕 50/页 + 总数 + 看板 60 秒快照（387 项测试全绿）并部署——2026-11-10，**已交付 tag v1.7.6**；✅ v1.7.7 限流计数原子化（P2）+ 认证后端插件化：`LoginFailureCounter` 独立表 + `select_for_update`（只锁已存在行，避免 gap 锁死锁；计数封顶）、`OA_AUTH_BACKENDS` dotted-path 有序链 + `ModelBackend` 垫底 + 契约校验纯函数 + 示例 Provider（用户名/邮箱，含 `is_active` 检查）（403 项测试全绿）并部署——2026-11-10，**已交付 tag v1.7.7**；✅ v1.7.8 审计字段统一：`AuditModel`（created_at/updated_at + created_by/updated_by）、`CurrentUserMiddleware`（匿名→None、finally 复位）、`pre_save` 自动填充；三批迁移覆盖 13/14 模型（structure 明确排除），迁移末尾 RunSQL 清除框架注入的时间默认值，历史行诚实为 NULL（410 项测试全绿）并部署——2026-11-10，**已交付 tag v1.7.8**；✅ v1.7.9 越权反馈语义统一（选 403）：`require_perm` 一处改动（31 视图 / 42 URL），已登录无权限 → 403 品牌页 / JSON `{code,message}`，未登录仍 302 带 next；同时修 `_error_response` 丢弃 `exception.message` 与日志只打 code （420 项测试）并部署——2026-11-11，**已交付 tag v1.7.9**；✅ v1.7.10 对象级越权统一：审批详情 GET/POST、附件下载、`approval_hide` 的对象级越权统一为 403（不存在仍 404），`services` 的 `PermissionError` 转 403 不再静默（427 项测试）并部署——2026-11-11，**已交付 tag v1.7.10**；✅ v1.7.11 匿名 JSON 401：`JsonAwareLoginRequiredMiddleware`（匿名 + 要 JSON → 401 `{code,message}`，HTML 仍 302 带 next）、JSON 判据收敛为 `wants_json()` 一处、`attendance_check` 的 302 改 403（433 项测试）并部署——2026-11-11，**已交付 tag v1.7.11**；下一步按 roadmap 第七节排期。

