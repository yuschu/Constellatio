# Constellatio · 企业办公自动化系统

> 基于 Django 的全栈插件化 OA —— **万物皆可插件**：容器唯一固定，从数据库/模板/图表等基础设施到审批/公告/考勤等业务模块全部可插拔、可替换。

一款基于 Django 的全栈插件化企业办公自动化系统。

## ✨ 特性

- 🧩 **万物皆可插件**：插件容器 + 全插件化业务（auth / user / approval / notice / attendance）
- 🔌 基础设施可插拔：数据库（MySQL↔sqlite）、模板引擎、主题 UI、图表引擎、认证后端
- 📋 审批中心：请假 / 报销 / 用章，状态机流转 + 全程留痕
- 📢 公告通知：发布 / 置顶 / 已读统计
- 🕐 考勤打卡：上下班打卡 + 月度统计看板（ECharts）
- ⛓ 区块链留痕：关键操作上链（SHA-256 哈希链），篡改即断链报警
- 🔐 RBAC 权限：部门 / 角色 / 权限，按角色动态收敛菜单
- 🐳 Docker 一键部署：`docker compose up -d`

## 🛠 技术栈

Python 3.11+ · Django 5.2 LTS · MySQL 8.0（可切 sqlite）· Risograph 印刷风主题 · ECharts 5 · Gunicorn · Nginx · Docker Compose

## 🚀 快速开始

### Docker 一键部署（推荐）

跨平台：**Windows / macOS / Linux** 通用，仅需安装 Docker（Desktop 或 Engine），一条命令拉起。

```bash
docker compose up -d
# 访问 http://localhost:80
```

### 本地开发

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## 📁 目录结构

```
Constellatio/
├── docker-compose.yml
├── Dockerfile
├── nginx/
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
│   └── blockchain/       # 操作留痕上链
├── themes/               # 主题插件层（可插拔）
│   └── risograph/        # Risograph 印刷风（默认主题插件）
└── docs/                 # 项目文档
    ├── tech-stack-and-architecture.md    # 技术栈与架构方案
    ├── constraints-and-acceptance.md     # 约束与验收规范
    ├── database-design.md                # 数据库设计文档
    ├── development-guide.md              # 开发指南（含编程规约/插件规范）
    ├── ai-assisted-development-guide.md  # AI 辅助开发规范（含迭代规范）
    └── project-overview.md               # 项目说明文档
```

## 📚 文档索引

**建议阅读顺序**：README → 技术栈与架构 → 约束与验收 → 数据库设计 → 开发指南 → AI 辅助开发规范 → 项目说明

| 文档 | 类型 | 内容 |
|---|---|---|
| [README.md](README.md)（本文件） | 总览 | 项目入口、特性、快速开始 |
| [docs/tech-stack-and-architecture.md](docs/tech-stack-and-architecture.md) | 设计 | 技术选型、全栈插件化架构、插件契约、竞品调研 |
| [docs/constraints-and-acceptance.md](docs/constraints-and-acceptance.md) | 规范 | 硬约束、功能边界、验收标准、开发规范、风险 |
| [docs/database-design.md](docs/database-design.md) | 设计 | 数据库设计（插件化：每插件独立表与迁移） |
| [docs/development-guide.md](docs/development-guide.md) | 开发 | 开发流程、环境、容器实现、插件开发、编程规约、插件规范 |
| [docs/ai-assisted-development-guide.md](docs/ai-assisted-development-guide.md) | 规范 | AI 辅助开发行为规范、迭代规范 |
| [docs/project-overview.md](docs/project-overview.md) | 说明 | 项目说明、使用指南、插件开发示例 |

## 📌 状态

**v0.3 已跑通**（审批中心：请假/报销/用章，状态机 + 全程留痕）→ 开发中：notice（v0.4）→ attendance（v0.5）→ blockchain（v0.6）→ 整合联调（v1.0）
