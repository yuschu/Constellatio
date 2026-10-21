# 技术栈与架构方案（全栈插件化）

> 项目：《基于 Django 的企业办公自动化系统的设计与实现》
> 设计思想：**万物皆可插件**——容器内核唯一固定，从基础设施到业务模块全部可插拔、可替换
> 文档版本：v1.1 · 2026-10-21

---

## 一、技术栈定版（全栈插件化）

| 层 | 组件 | 默认实现 | 可插拔机制 |
|---|---|---|---|
| 运行时 | Python | 3.11+ | — |
| **插件容器** | **Django** | 5.2 LTS | 内核固定，提供注册表/外壳/信号总线 |
| **数据库引擎** | **MySQL 8.0** | 默认 | Django 原生支持 mysql / sqlite / postgres / oracle **后端切换**；每插件可挂独立数据源（database router） |
| ORM | Django ORM | 随框架 | 每插件自带 models + migrations，各自建表 |
| **模板引擎** | Django 模板 | 默认 | `TEMPLATES` 配置可切 Jinja2 / 多引擎共存 |
| **主题 UI** | **Risograph 印刷风**（Bootstrap 栅格） | 默认主题插件 `themes/risograph` | 主题即插件：新建 `themes/<name>/` + 改 `OA_THEME` 即换主题 |
| **图表引擎** | **ECharts** | 默认图表插件 | 统一 chart 接口，可换 Chart.js / D3 / 原生 SVG |
| **认证后端** | Django auth（session） | 默认 | `AUTHENTICATION_BACKENDS` 可插拔：加 LDAP / OAuth 插件 |
| 事件总线 | Django signals | 随框架 | 插件间通信，互不 import |
| WSGI | Gunicorn | 默认 | 可换 uvicorn（ASGI） |
| 代理/部署 | Nginx + Docker Compose | 默认 | `docker compose up -d` 一键部署 |

## 二、全栈插件化架构

```
┌─────────────────────────────────────────────────────────┐
│ 业务插件层（全部可插拔）                                    │
│  auth 认证 │ user 用户/RBAC │ approval 审批 │ notice 公告 │ attendance 考勤 │ blockchain 留痕 │ + 未来任意插件 │
├─────────────────────────────────────────────────────────┤
│ 基础设施插件层（官方原生可插拔机制）                         │
│  DB 后端(mysql/sqlite/pg) │ 模板引擎(Django/Jinja2)       │
│  主题 UI(Bootstrap/Tailwind) │ 图表引擎(ECharts/Chart.js) │
│  认证后端(session/LDAP/OAuth)                             │
├─────────────────────────────────────────────────────────┤
│ 插件容器 plugin_host（唯一固定）                           │
│  Plugin Registry │ 自动发现(AppConfig.ready) │ 统一外壳    │
│  信号总线 signals │ 配置中心 │ 权限聚合 │ 模板基座          │
├─────────────────────────────────────────────────────────┤
│ 部署：Nginx → Gunicorn → Django 容器 + MySQL 8.0 容器     │
│        docker compose up -d                               │
└─────────────────────────────────────────────────────────┘
```

### 分层职责

1. **插件容器 plugin_host**（唯一固定核心）
   - 插件注册与自动发现（`OA_PLUGINS` 声明 + `AppConfig.ready()` 扫描）
   - 统一外壳：登录、导航、布局、模板基座
   - 信号总线（Django signals）、权限聚合、配置中心
2. **基础设施插件层**（Django 官方原生可插拔机制）
   - 数据库后端：`DATABASES` 一行切换 mysql ↔ sqlite ↔ postgres
   - 模板引擎：`TEMPLATES` 配置可切 Django 模板 ↔ Jinja2
   - 主题 UI：主题即插件（默认 `themes/risograph`），换主题 = 新建 `themes/<name>/`（模板基座 + 静态资源）+ 改 `OA_THEME`
   - 图表引擎：统一 `ChartRenderer` 接口，ECharts 为默认实现
   - 认证后端：`AUTHENTICATION_BACKENDS` 列表加一行 = 新增一种登录方式
3. **业务插件层**（全部可插拔）
   - auth（登录/认证）、user（用户/部门/角色/RBAC）、approval（审批中心）、notice（公告通知）、attendance（考勤打卡）、blockchain（操作留痕上链）
   - 删一个插件 = 从 `OA_PLUGINS` 删一行，导航/权限/路由自动消失，系统照常运行

## 三、插件契约（每个插件必须声明）

```
PluginMeta:
  name          # 插件名
  version       # 版本
  menus         # 贡献的导航菜单（容器聚合渲染）
  permissions   # 贡献的权限码（容器合并进 RBAC 校验）
  urls          # 路由（挂载到 /plugins/<name>/）
  signals       # 订阅/发出的信号
  templates     # 模板片段（继承容器基座）
  models        # 数据模型（自带迁移）
```

**容器职责**：扫描注册 → 聚合菜单/权限 → 渲染外壳 → 转发请求到插件。

## 四、功能模块（4 个核心业务插件）

| 插件 | 功能 | 核心数据表 |
|---|---|---|
| auth | 登录/认证 | auth 相关表 |
| user | 用户/部门/角色/RBAC | department、user、role、user_role |
| approval | 审批中心（请假/报销/用章，状态机+审批留痕） | approval、approval_record |
| notice | 公告通知（发布/置顶/已读） | announcement、announcement_read |
| attendance | 考勤打卡（打卡+月度统计） | attendance |
| blockchain | 操作留痕上链（SHA-256 哈希链，防篡改审计） | blockchain_record |

## 五、关键设计决策

1. **全栈插件化**：Django 官方原生机制（database backends / template backends / auth backends）+ 自研 Plugin Registry，实现从基础设施到业务模块的万物可插拔
2. **单体 + 插件化**：规模 ≤500 人单服务器，微服务是过度设计；Django app 机制实现"可拆可合"（呼应泛微 e10 / 若依 / 飞书客户端模块化思想，但轻量级）
3. **不引前端框架**：Django 模板 + Bootstrap 足够，减少技术栈复杂度，突出后端架构设计
4. **RBAC 由 user 插件统一提供**：所有业务插件共用一套权限
5. **审批状态机**：approval.status + approval_record 双表，实现审批流转与全程留痕（发起→审批中→通过/驳回→归档）
6. **操作留痕上链**：blockchain 插件订阅全局信号，用 SHA-256 哈希链记录关键操作（链式哈希防篡改，完整性可随时校验），实现"业务留痕 + 篡改可检测"的审计能力
7. **容器化部署**：docker compose up -d 一键拉起，环境一致、可复现

## 六、竞品调研结论

- **飞书**（字节）：Go 微服务（Hertz+Kitex/CloudWeGo），自研容器平台 TCE；客户端 33 模块插件化组织
- **钉钉**（阿里）：Java 微服务 + 单元化架构（Envoy 网关 + gRPC）；考勤/审批一体化
- **企业微信**（腾讯）：连接微信生态，客户运营定位
- **泛微 e-cology 10**：J2EE（EJB/JMS）+ Struts → 演进为 200+ 微服务"可拆可合"；信创适配强
- **蓝凌 EKP**：Java Spring MVC；知识管理/集成引擎强
- **通达 OA**：PHP + MySQL + Nginx；70% 源码开放
- **O2OA**（开源）：Java 系，五大引擎，AGPL 100% 开源，Docker 一键部署
- **RuoYi Office**（开源）：SpringCloud + Vue3 + Vben，模块化按需启用

**空白点**：现有 OA 两极分化——大厂 SaaS 重/贵/数据上云，传统厂商技术栈旧/实施周期长，开源以 Java 系为主；本项目用 **Python/Django 全栈插件化轻量 OA** 补足中小企业/高校轻量自建空白。

## 七、部署方案（Docker 一键部署）

```
docker-compose.yml
├── nginx     （反向代理 + 静态文件）
├── web       （Gunicorn + Django 容器）
└── db        （MySQL 8.0）
```

启动：`docker compose up -d`

> **跨平台**：Windows / macOS / Linux 通用，仅需安装 Docker（Desktop / Engine），无需其他环境即可一键部署。

## 八、项目亮点

- **设计亮点**："基于 Django 的全栈插件化架构——从基础设施到业务模块万物皆可插拔的可扩展 OA 系统"
- **功能演示**：
  1. 停掉 approval 插件 → 导航消失、系统照常跑
  2. 数据库 MySQL → SQLite 一行切换重启即跑
  3. 新增会议室插件（写 models+views+meta）→ 注册一行 → 系统自动出现该模块
  4. 篡改一条上链记录 → 链完整性校验立即报警（区块链留痕防篡改）
- **呼应竞品**：飞书客户端 33 模块 / 泛微"可拆可合" / 若依按需启用——本项目实现最彻底

## 九、开发排期（9 周）

| 周次 | 任务 |
|---|---|
| 1-2 | 需求分析 + 系统设计 + 全栈插件化架构设计 |
| 3-4 | 插件容器 plugin_host + auth/user 插件（RBAC） |
| 5 | approval 审批中心插件 |
| 6 | notice 公告插件 |
| 7 | attendance 考勤插件 + ECharts 统计看板 |
| 8 | blockchain 留痕插件 + 链完整性校验 |
| 9 | 模块整合联调 + 测试 + Docker 部署 + 正式发布 |
