# Constellatio · Enterprise Office Automation

**English** | [简体中文](#简体中文)

> **flexible plugin** — a full-stack, plugin-driven OA built on Django. The plugin container is the only fixed layer: infrastructure such as the database, themes, templates, charting, and authentication, together with business modules such as approvals, notices, and attendance, is fully pluggable and replaceable.

**Current baseline**: `v2.2.15` (2026-11-15) · 650+ automated tests passing · tag `v2.2.15` · Release `v2.2.15 Beta` ("AI Assistant C1: single-action approval card")
**Workspace**: assistant composer attachments, read-only mode, and model status are in place · 650+ automated tests passing

## ✨ Features

### Architecture and platform

* 🧩 **Plugin-first**: a plugin container plus fully pluginized business capabilities (auth / user / approval / notice / attendance / blockchain / workspace / structure / language)
* 🔌 **Pluggable infrastructure**: database (MySQL ↔ SQLite), appearance (built-in light/dark + `themes/` theme packs), template engine, chart engine, and authentication backend
* ⚙ **Runtime plugin switches**: enabling or disabling a plugin takes effect immediately; a disabled plugin hides its menus and returns 404, and the change is recorded in the activity log
* 🏠 **Workspace and charts**: metric cards, workflow trends, plugin distribution, and organization charts with today / week / month linkage and separate admin / employee views; ECharts is bundled locally, and the chart engine can be disabled at runtime with automatic table fallback
* ⛓ **Activity log**: key operations are recorded in a SHA-256 hash chain, each entry has a detail view, and tampering breaks the chain and raises an alert; statistics are grouped by day × source plugin
* 🔑 **Enterprise SSO**: HMAC-signed ticket gateway login with automatic account provisioning and replay protection, coexisting with password login
* ✉ **Notifications**: an unread badge in the top bar plus a message center; pending approval tasks, approval results, and published notices generate in-app messages, and the feature can be disabled with graceful fallback
* 🤖 **Built-in AI assistant (A/B/C1)**: Compose bundles Ollama and `qwen3:4b`, pulled and prewarmed on first start, with automatic fallback to the ModelScope non-thinking variant if the official source fails; read-only queries, six approval draft cards (inline editing, with submission still posting to the original approval endpoints), and ordinary single-action approval cards (card only; confirmation still POSTs to the existing approval detail endpoint); conversations are persisted; the configuration page can override the model with a gateway or a larger model
* 📦 **Self-hosted deployment**: `docker compose up -d` starts the full stack (MySQL 8 + Ollama + Gunicorn + WhiteNoise); Bootstrap is vendored for offline use, startup is refused without `SECRET_KEY` in production, and logout uses POST

### Business capabilities

* 📋 **Approval center**: six dynamic forms for leave, reimbursement, seal use, field work, overtime, and compensatory time off, with required-field markers and automatic assignment / CC to the direct manager
* 🕐 **Attendance**: office and field check-in, makeup check-in, detail filters, and a monthly dashboard; attendance rules are configurable (working hours, late/early grace periods, workdays, and makeup lookback). Since v2.2, the dashboard follows the Jibble layout, with four-column detail filters and a month selector that follows the selected range
* 📢 **Notices**: a single-column notice feed with the title and body on the same screen; notices are marked read on entry, and read details are available to administrators
* 🏢 **Organization and permissions**: a functional organization template (one-click idempotent application of departments / roles / users), countersigned soft and hard department deletion, a user state machine, L0–L3 permission codes, and role-template grants; menus and URLs use the same policy
* 👤 **Profile**: a top-bar username entry for editing the profile, viewing permissions, and changing the password; user editing only exposes permissions that the operator can grant
* 🧾 **Baseline access**: attendance check-in and notice browsing are available to every signed-in user; administrative roles additionally get attendance report details (`attendance_report_view`)

### Frontend and experience

* 🖥 **DSH-style frontend (v2.2.0–v2.2.13)**: the sidebar's wide and narrow states, settings sheet, composer, plugin page, dashboard, attendance, site-wide scrollbars, and page transitions are aligned item by item with the DSH source; dashboard spacing is tightened
* 🎨 **Theme consolidation**: the built-in themes are light and dark, controlled by one site-wide switch; additional themes are installed under `themes/<key>/theme.json` and automatically appear in the "Theme packs" row

### Security and engineering

* 🛡 **Security baseline**: row locks and transactions for approval, audit, and attendance writes; object-level authorization for approval details and attachments by applicant / approver / countersigner / CC; unified 401 / 403 / 404 / 500 semantics with `X-Request-Id`; login rate limiting and password validators; a CSP with 10 directives and a nonce-only `script-src`, without enabling `unsafe-inline`
* 🧪 **Engineering gates**: pinned dependencies + `ruff` + `manage.py check` + full test suite in GitHub Actions, with 650+ tests passing; the shared cache uses `DatabaseCache`, so login rate limiting and SSO replay protection hold across workers

## 🛠 Tech stack

Python 3.13 · Django 5.2 LTS · MySQL 8.0 (SQLite switchable) · built-in themes (light / dark, `themes/corporate-clean`) · ECharts 5 · Gunicorn · WhiteNoise · Docker Compose

## 🚀 Quick start

### Docker (recommended)

Cross-platform: **Windows / macOS / Linux**, with only Docker (Desktop or Engine) required.

```bash
cp .env.example .env           # set SECRET_KEY; use an OLLAMA_IMAGE mirror if Docker Hub is slow
docker compose up -d --build
# open http://localhost:8000
# default superuser: admin / Constellatio@2026 (override in .env; see .env.example)
# first start pulls and prewarms the bundled qwen3:4b (~2–3 GB); falls back to the ModelScope non-thinking variant if the official source fails
# CPU inference: about 2–4 minutes per turn for the official build, about 3–6 seconds for the non-thinking fallback; with a GPU, switch to a gateway or a larger model on the configuration page
```

### Local development

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable   # cache table; a missing table makes login return 500 (login limiting / SSO replay protection use the shared cache)
python manage.py createsuperuser
python manage.py runserver
```

## 📁 Project layout

```text
Constellatio/
├── docker-compose.yml   # one-command stack (MySQL 8 + Ollama + web)
├── Dockerfile           # application image (gunicorn + whitenoise)
├── entrypoint.sh        # container entrypoint (migrate / collectstatic / superuser / gunicorn)
├── .env.example         # deployment environment template
├── requirements.txt
├── manage.py
├── plugin_host/          # plugin container (the only fixed core)
│   ├── registry.py       # plugin registry (PluginMeta / menu aggregation)
│   ├── discover.py       # auto-discovery and registration checks
│   ├── signals.py        # signal bus (cross-plugin communication)
│   ├── context_processors.py  # aggregated menu injection for templates
│   ├── views.py          # workspace home
│   └── apps.py           # container AppConfig
├── plugins/              # business plugins (all removable)
│   ├── auth/             # authentication plugin
│   ├── user/             # users / departments / roles / RBAC
│   ├── approval/         # approval center
│   ├── notice/           # notices
│   ├── attendance/       # attendance
│   ├── blockchain/       # activity hash chain
│   ├── workspace/        # runtime plugin switches
│   ├── structure/        # functional organization template
│   └── language/         # language packs
├── themes/               # theme layer (pluggable, discovered via theme.json)
│   └── corporate-clean/  # built-in theme: light + dark
├── locale/               # translation catalogs (.po and .mo committed; run tools/compile_mo.py after editing .po)
├── tools/                # pure-Python .mo compiler
└── docs/                 # project docs (core docs + frontend / AI plans + plugin development and release history)
```

## 📚 Documentation

**Suggested reading order**: README → Tech stack and architecture → Constraints and acceptance → Database design → Development guide → AI-assisted development guide → Project overview → Frontend refactor record

Most project documentation is written in Chinese.

### Core documents

| Document | Contents |
| --- | --- |
| [docs/release-notes.md](docs/release-notes.md) | **Release hub**: current v2.2.15 baseline, release history, tag checkout guide, and upgrade notes |
| [docs/tech-stack-and-architecture.md](docs/tech-stack-and-architecture.md) | Technology choices, full-stack plugin architecture, plugin contracts, and competitor research |
| [docs/constraints-and-acceptance.md](docs/constraints-and-acceptance.md) | Hard constraints, feature boundaries, acceptance criteria, development standards, and risks |
| [docs/database-design.md](docs/database-design.md) | Database design (pluginized: independent tables and migrations per plugin) |
| [docs/development-guide.md](docs/development-guide.md) | Development workflow, environment, container implementation, plugin development, and coding conventions |
| [docs/ai-assisted-development-guide.md](docs/ai-assisted-development-guide.md) | AI-assisted development behavior and iteration standards |
| [docs/project-overview.md](docs/project-overview.md) | Project overview, usage guide, and plugin development examples |
| [docs/roadmap.md](docs/roadmap.md) | Gap matrix, v1.5–v2.2.15 roadmap, fixes, and documentation debt |

### Frontend and AI plans

| Document | Contents |
| --- | --- |
| [docs/frontend-refactor-plan.md](docs/frontend-refactor-plan.md) | v2.2.0–v2.2.13 DSH implementation record and acceptance data (§9.13.27–41) |
| [docs/dsh-visual-spec.md](docs/dsh-visual-spec.md) | Measured DSH literals: color / spacing / components / shortcut visual baseline |
| [docs/ai-assistant-plan.md](docs/ai-assistant-plan.md) | Conversational home A→B→C plan; A/B and C1 ordinary single-action cards are shipped, countersigned requests remain to be designed |
| [docs/ai-assistant-eval.md](docs/ai-assistant-eval.md) | A-phase 20 fixed questions, scoring rules, run instructions, and 4B / 70% acceptance boundary |
| [docs/ai-assistant-config.md](docs/ai-assistant-config.md) | Built-in Ollama default, configuration override, database / environment precedence, API key encryption, connection testing, and data flow |
| [docs/ai-tool-calling.md](docs/ai-tool-calling.md) | Local-model tool calling conventions; A-phase read-only tools and validation layer are shipped |

### Plugin development and release history

- **Plugin development**: [workspace](docs/plugin-dev-workspace.md) / [user](docs/plugin-dev-user.md) / [structure](docs/plugin-dev-structure.md) / [language](docs/plugin-dev-language.md) / [theme](docs/plugin-dev-theme.md) / [RBAC](docs/plugin-dev-rbac.md) / [SSO](docs/plugin-dev-sso.md) / [notifications](docs/plugin-dev-notify.md)
- **Release history**: 59 `docs/plugin-dev-*.md` documents (8 plugin topics + 51 version records), each recording the state at delivery time rather than being rewritten against the current baseline; see the `docs/` directory for the full list and [release-notes](docs/release-notes.md) for the entry point

## 📌 Status

**v2.2.15 AI Assistant C1 single-action approval card shipped** (2026-11-15): an ordinary approval request produces a read-only action card in the conversation, and the card POSTs directly to the existing `approval_detail`; nothing is written until the user confirms. No new write tools, endpoints, or migrations; countersigned requests do not produce cards. 650+ tests pass; tag `v2.2.15` and Release `v2.2.15 Beta` are published, with `Latest` pointing to the release. See [docs/release-notes.md](docs/release-notes.md) for the full version record and upgrade notes.

---

## 简体中文

> **flexible plugin** —— 基于 Django 的全栈插件化 OA。插件容器是唯一固定层：数据库、外观、模板、图表、认证等基础设施，以及审批、公告、考勤等业务模块，全部可插拔、可替换。

**当前基线**：`v2.2.15`（2026-11-15）· 650+ 项自动化测试全绿 · tag `v2.2.15` · Release `v2.2.15 Beta`（「AI 助手 C1 普通单动作卡」）
**工作区**：首页 composer 的附件、只读模式、模型状态已补齐 · 650+ 项测试全绿

## ✨ 特性

### 架构与平台

* 🧩 **万物皆可插件**：插件容器 + 全插件化业务（auth / user / approval / notice / attendance / blockchain / workspace / structure / language）
* 🔌 **基础设施可插拔**：数据库（MySQL ↔ SQLite）、外观（内置浅色 / 深色 + `themes/` 外观包）、模板引擎、图表引擎、认证后端
* ⚙ **运行时插件开关**：工作台启用 / 禁用插件即时生效，停用即隐藏菜单 + 404；操作进入活动记录
* 🏠 **工作台与图表**：指标卡、流程趋势、插件分布 / 组织人员图表，今日 / 本周 / 本月联动，管理员 / 员工视图分流；ECharts 本地资源，图表引擎可运行时停用并自动降级表格
* ⛓ **活动记录**：关键操作 SHA-256 哈希链留痕，单条可查详情，篡改即断链报警；按日 × 来源插件统计
* 🔑 **企业 SSO**：HMAC 签名 Ticket 网关登录，自动建号 / 防重放，与账号密码登录并存
* ✉ **消息提醒**：顶栏未读数 + 消息中心；审批待办 / 结果、公告发布自动站内信，可停用降级
* 🤖 **内置 AI 助手（A/B/C1 阶段）**：Compose 自带 Ollama 与 `qwen3:4b`，首次启动自动拉取并预热；官方源失败自动切 ModelScope 非思考版回退；只读查询 + 六类审批草稿卡片（卡片内联编辑，提交仍回原审批端点）+ 普通单待审批动作卡（只出卡，确认后仍 POST 原审批详情端点）；会话落库；配置页可覆盖为网关或更大模型
* 📦 **私有化部署**：`docker compose up -d` 一键拉起（MySQL 8 + Ollama + Gunicorn + WhiteNoise）；Bootstrap 离线化、生产缺 `SECRET_KEY` 拒绝启动、登出改 POST

### 业务能力

* 📋 **审批中心**：请假 / 报销 / 用章 / 外出 / 加班 / 调休六类动态表单，必填标注，直属上级自动指派与抄送
* 🕐 **考勤打卡**：内勤 / 外勤签到、补卡、签到详情筛选、月度看板；考勤规则可配（上下班时间 / 迟到早退宽限 / 工作日 / 补卡回溯）。v2.2 起采用 Jibble 形态仪表盘，签到详情四列筛选、月份跟随区间
* 📢 **公告通知**：单列公告流，标题与正文同屏；进入即已读，已读明细下沉管理岗
* 🏢 **组织与权限**：职能制组织架构模板（部门 / 角色 / 用户一键幂等应用）、部门软删 / 硬删会签、用户状态机、权限码 L0–L3 与角色模板授权，菜单与 URL 同一口径
* 👤 **个人中心**：顶栏用户名入口；编辑资料 / 查看权限 / 修改密码；用户编辑只展示操作者可授予的权限范围
* 🧾 **全员基线**：考勤打卡与公告浏览登录即用；管理岗额外拥有签到详情（`attendance_report_view`）

### 前端与体验

* 🖥 **DSH 化前端（v2.2.0–v2.2.13）**：侧栏宽窄两态与设置弹层、输入框、插件页、看板、考勤、全站滚动条、页面切换按 DSH 源码逐项对齐；看板布局收紧
* 🎨 **外观收口**：内置外观即浅色 / 深色，设置里一个开关全站生效；更多外观放 `themes/<key>/theme.json` 装包，自动出现在「外观包」行

### 安全与工程

* 🛡 **安全基线**：审批 / 留痕 / 打卡关键写入行锁 + 事务；审批详情与附件按申请人 / 审批人 / 会签人 / 抄送人对象级鉴权；统一 401 / 403 / 404 / 500 语义与 `X-Request-Id`；登录失败限流 + 密码校验器；CSP 10 条指令，`script-src` 只认 nonce，不放开 `unsafe-inline`
* 🧪 **工程门禁**：依赖精确版本 + `ruff` + `manage.py check` + GitHub Actions 全量测试，当前 650+ 项全绿；共享缓存走 `DatabaseCache`，登录限流与 SSO 防重放跨 worker 成立

## 🛠 技术栈

Python 3.13 · Django 5.2 LTS · MySQL 8.0（可切 SQLite）· 内置外观（浅色 / 深色，`themes/corporate-clean`）· ECharts 5 · Gunicorn · WhiteNoise · Docker Compose

## 🚀 快速开始

### Docker 一键部署（推荐）

跨平台：**Windows / macOS / Linux** 通用，仅需安装 Docker（Desktop 或 Engine）。

```bash
cp .env.example .env           # 填 SECRET_KEY；Docker Hub 慢可改 OLLAMA_IMAGE 镜像站
docker compose up -d --build
# 访问 http://localhost:8000
# 默认超管：admin / Constellatio@2026（可用 .env 覆盖，见 .env.example）
# 首次启动会拉取并预热内置 qwen3:4b（约 2–3 GB）；官方源失败自动切 ModelScope 非思考版回退
# CPU 推理：官方件单轮约 2–4 分钟，回退件关闭思考后约 3–6 秒；有 GPU 可在配置页改网关或更大模型
```

### 本地开发

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable   # 缓存表；缺表登录会 500（登录限流 / SSO 防重放走共享缓存）
python manage.py createsuperuser
python manage.py runserver
```

## 📁 目录结构

```text
Constellatio/
├── docker-compose.yml   # 一键部署（MySQL 8 + Ollama + web）
├── Dockerfile           # 应用镜像（gunicorn + whitenoise）
├── entrypoint.sh        # 容器启动脚本（migrate / collectstatic / 超管 / gunicorn）
├── .env.example         # 部署环境变量示例
├── requirements.txt
├── manage.py
├── plugin_host/          # 插件容器（唯一固定核心）
│   ├── registry.py       # 插件注册表（PluginMeta / 菜单聚合）
│   ├── discover.py       # 自动发现与注册校验
│   ├── signals.py        # 信号总线（跨插件通信）
│   ├── context_processors.py  # 模板注入聚合菜单
│   ├── views.py          # 工作台首页
│   └── apps.py           # 容器 AppConfig
├── plugins/              # 业务插件（全部可插拔）
│   ├── auth/             # 认证插件
│   ├── user/             # 用户 / 部门 / 角色 / RBAC
│   ├── approval/         # 审批中心
│   ├── notice/           # 公告通知
│   ├── attendance/       # 考勤打卡
│   ├── blockchain/       # 操作留痕上链
│   ├── workspace/        # 运行时插件开关
│   ├── structure/        # 职能制组织架构模板
│   └── language/         # 语言包
├── themes/               # 外观层（可插拔，theme.json 发现）
│   └── corporate-clean/  # 内置外观：浅色 + 深色两态
├── locale/               # 翻译目录（.po 与 .mo 都入库；改 .po 后跑 tools/compile_mo.py）
├── tools/                # 纯 Python .mo 编译器
└── docs/                 # 项目文档（核心文档 + 前端 / AI 规划 + 插件开发与历史版本记录）
```

## 📚 文档索引

**建议阅读顺序**：README → 技术栈与架构 → 约束与验收 → 数据库设计 → 开发指南 → AI 辅助开发规范 → 项目说明 → 前端重构记录

### 核心文档

| 文档 | 内容 |
| --- | --- |
| [docs/release-notes.md](docs/release-notes.md) | **发版总入口**：v2.2.15 当前基线、历史收口、按 tag 检出指路、升级须知 |
| [docs/tech-stack-and-architecture.md](docs/tech-stack-and-architecture.md) | 技术选型、全栈插件化架构、插件契约、竞品调研 |
| [docs/constraints-and-acceptance.md](docs/constraints-and-acceptance.md) | 硬约束、功能边界、验收标准、开发规范、风险 |
| [docs/database-design.md](docs/database-design.md) | 数据库设计（插件化：每插件独立表与迁移） |
| [docs/development-guide.md](docs/development-guide.md) | 开发流程、环境、容器实现、插件开发、编程规约 |
| [docs/ai-assisted-development-guide.md](docs/ai-assisted-development-guide.md) | AI 辅助开发行为规范、迭代规范 |
| [docs/project-overview.md](docs/project-overview.md) | 项目说明、使用指南、插件开发示例 |
| [docs/roadmap.md](docs/roadmap.md) | 差距矩阵、v1.5–v2.2.15 迭代路线、修复项与文档债务 |

### 前端与 AI 规划

| 文档 | 内容 |
| --- | --- |
| [docs/frontend-refactor-plan.md](docs/frontend-refactor-plan.md) | v2.2.0–v2.2.13 DSH 化实施记录与验收数据（§9.13.27–41） |
| [docs/dsh-visual-spec.md](docs/dsh-visual-spec.md) | DSH 实测字面量：颜色 / 间距 / 组件 / 快捷键视觉基线 |
| [docs/ai-assistant-plan.md](docs/ai-assistant-plan.md) | 对话式首页 A→B→C 阶段方案；A/B 阶段已落地，C1 普通单动作卡已落地，会签单待设计 |
| [docs/ai-assistant-eval.md](docs/ai-assistant-eval.md) | A 阶段 20 条固定问句、评分口径、运行方式与 4B/70% 验收边界 |
| [docs/ai-assistant-config.md](docs/ai-assistant-config.md) | 内置 Ollama 默认、配置页覆盖、数据库 / 环境变量优先级、API Key 加密、测试连接与数据流向 |
| [docs/ai-tool-calling.md](docs/ai-tool-calling.md) | 本地模型 tool calling 接入规范；A 阶段只读工具与校验层已落地 |

### 插件开发与历史版本

- **插件开发**：[workspace](docs/plugin-dev-workspace.md) / [user](docs/plugin-dev-user.md) / [structure](docs/plugin-dev-structure.md) / [language](docs/plugin-dev-language.md) / [theme](docs/plugin-dev-theme.md) / [RBAC](docs/plugin-dev-rbac.md) / [SSO](docs/plugin-dev-sso.md) / [消息提醒](docs/plugin-dev-notify.md)
- **历史版本**：`docs/plugin-dev-*.md` 共 59 篇（8 篇插件专题 + 51 篇版本记录），按版本记录交付时状态，不随当前基线回改；完整清单见 `docs/` 目录，统一入口见 [release-notes](docs/release-notes.md)

## 📌 状态

**v2.2.15 AI 助手 C1 普通单动作卡已交付并发布**（2026-11-15）：普通审批单在对话内生成只读动作卡，卡片直接 POST 原 `approval_detail`，用户点击后才写库；无新写工具、无新端点、无迁移；会签单不出卡。650+ 项测试全绿；tag `v2.2.15`，Release `v2.2.15 Beta` 已发布并接管 `Latest`。完整版本记录与升级须知见 [docs/release-notes.md](docs/release-notes.md)。
