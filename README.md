# Constellatio・企业办公自动化系统

> 基于 Django 的全栈插件化 OA。容器唯一固定：数据库、外观、模板、图表、认证等基础设施，与审批、公告、考勤等业务模块，全部可插拔、可替换。

**当前基线**：`v2.2.13`（2026-11-14）· 564 项测试全绿 · tag `v2.2.13` · Release `v2.2.13 Beta`（「视觉风格重构」）

## ✨ 特性

### 架构与平台

* 🧩 **万物皆可插件**：插件容器 + 全插件化业务（auth / user / approval / notice / attendance / blockchain / workspace / structure / language）
* 🔌 **基础设施可插拔**：数据库（MySQL ↔ sqlite）、外观（内置浅色/深色 + `themes/` 外观包）、模板引擎、图表引擎、认证后端
* ⚙ **运行时插件开关**：工作台启用 / 禁用插件即时生效，停用即隐藏菜单 + 404；操作进入活动记录
* 🏠 **工作台与图表**：指标卡、流程趋势、插件分布 / 组织人员图表，今日 / 本周 / 本月联动，管理员 / 员工视图分流；ECharts 本地资源，图表引擎可运行时停用并自动降级表格
* ⛓ **活动记录**：关键操作 SHA-256 哈希链留痕，单条可查详情，篡改即断链报警；按日 × 来源插件统计
* 🔑 **企业 SSO**：HMAC 签名 Ticket 网关登录，自动建号 / 防重放，与账号密码登录并存
* ✉ **消息提醒**：顶栏未读数 + 消息中心；审批待办 / 结果、公告发布自动站内信，可停用降级
* 📦 **私有化部署**：`docker compose up -d` 一键拉起（MySQL 8 + Gunicorn + WhiteNoise）；Bootstrap 离线化、生产缺 `SECRET_KEY` 拒绝启动、登出改 POST

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
* 🧪 **工程门禁**：依赖精确版本 + `ruff` + `manage.py check` + GitHub Actions 全量测试，当前 564 项全绿；共享缓存走 `DatabaseCache`，登录限流与 SSO 防重放跨 worker 成立

## 🛠 技术栈

Python 3.13・Django 5.2 LTS・MySQL 8.0（可切 sqlite）・内置外观（浅色 / 深色，`themes/corporate-clean`）・ECharts 5・Gunicorn・WhiteNoise・Docker Compose

## 🚀 快速开始

### Docker 一键部署（推荐）

跨平台：**Windows / macOS / Linux** 通用，仅需安装 Docker（Desktop 或 Engine）。

```bash
docker compose up -d --build
# 访问 http://localhost:8000
# 默认超管：admin / Constellatio@2026（可用 .env 覆盖，见 .env.example）
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
├── docker-compose.yml   # 一键部署（MySQL8 + web）
├── Dockerfile           # 应用镜像（gunicorn + whitenoise）
├── entrypoint.sh        # 容器启动脚本（migrate/collectstatic/超管/gunicorn）
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
│   └── language/         # 中英文切换
├── themes/               # 外观层（可插拔，theme.json 发现）
│   └── corporate-clean/  # 内置唯一外观：浅色 + 深色两态
├── locale/               # 翻译目录（.po 与 .mo 都入库；改 .po 后跑 tools/compile_mo.py）
├── tools/                # 纯 Python .mo 编译器
└── docs/                 # 项目文档（核心文档 + 前端 / AI 规划 + 插件开发与历史版本记录）
```

## 📚 文档索引

**建议阅读顺序**：README → 技术栈与架构 → 约束与验收 → 数据库设计 → 开发指南 → AI 辅助开发规范 → 项目说明 → 前端重构记录

### 核心文档

| 文档 | 内容 |
| --- | --- |
| [docs/release-notes.md](docs/release-notes.md) | **发版总入口**：v2.2.13 当前基线、历史收口、按 tag 检出指路、升级须知 |
| [docs/tech-stack-and-architecture.md](docs/tech-stack-and-architecture.md) | 技术选型、全栈插件化架构、插件契约、竞品调研 |
| [docs/constraints-and-acceptance.md](docs/constraints-and-acceptance.md) | 硬约束、功能边界、验收标准、开发规范、风险 |
| [docs/database-design.md](docs/database-design.md) | 数据库设计（插件化：每插件独立表与迁移） |
| [docs/development-guide.md](docs/development-guide.md) | 开发流程、环境、容器实现、插件开发、编程规约 |
| [docs/ai-assisted-development-guide.md](docs/ai-assisted-development-guide.md) | AI 辅助开发行为规范、迭代规范 |
| [docs/project-overview.md](docs/project-overview.md) | 项目说明、使用指南、插件开发示例 |
| [docs/roadmap.md](docs/roadmap.md) | 差距矩阵、v1.5–v2.2.13 迭代路线、修复项与文档债务 |

### 前端与 AI 规划

| 文档 | 内容 |
| --- | --- |
| [docs/frontend-refactor-plan.md](docs/frontend-refactor-plan.md) | v2.2.0–v2.2.13 DSH 化实施记录与验收数据（§9.13.27–41） |
| [docs/dsh-visual-spec.md](docs/dsh-visual-spec.md) | DSH 实测字面量：颜色 / 间距 / 组件 / 快捷键视觉基线 |
| [docs/ai-assistant-plan.md](docs/ai-assistant-plan.md) | 对话式首页 A→B→C 阶段方案（未实施） |
| [docs/ai-tool-calling.md](docs/ai-tool-calling.md) | 本地模型 tool calling 接入与确认闸门（未实施） |

### 插件开发与历史版本

- **插件开发**：[workspace](docs/plugin-dev-workspace.md) / [user](docs/plugin-dev-user.md) / [structure](docs/plugin-dev-structure.md) / [language](docs/plugin-dev-language.md) / [theme](docs/plugin-dev-theme.md) / [RBAC](docs/plugin-dev-rbac.md) / [SSO](docs/plugin-dev-sso.md) / [消息提醒](docs/plugin-dev-notify.md)
- **历史版本**：`docs/plugin-dev-*.md` 共 59 篇（8 篇插件专题 + 51 篇版本记录），按版本记录交付时状态，不随当前基线回改；完整清单见 `docs/` 目录，统一入口见 [release-notes](docs/release-notes.md)

## 📌 状态

**v2.2.13 视觉风格重构已交付并发布**（2026-11-14）：看板 / 考勤 / 前端外壳 / 滚动条收口完成，564 项测试全绿；tag `v2.2.13` → `3fcf217`，Release `v2.2.13 Beta` 已发布并接管 `Latest`；无新增数据库迁移。完整版本记录与升级须知见 [docs/release-notes.md](docs/release-notes.md)。
