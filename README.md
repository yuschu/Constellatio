# Constellatio・企业办公自动化系统

> 基于 Django 的全栈插件化 OA ——
>
> **万物皆可插件**
>
> ：容器唯一固定，从数据库 / 模板 / 图表等基础设施到审批 / 公告 / 考勤等业务模块全部可插拔、可替换。

一款基于 Django 的全栈插件化企业办公自动化系统。

## ✨ 特性



* 🧩 **万物皆可插件**：插件容器 + 全插件化业务（auth / user / approval / notice / attendance / blockchain / workspace / structure / language）

* 🔌 基础设施可插拔：数据库（MySQL↔sqlite）、主题 UI（Corporate Clean / Risograph）、模板引擎、图表引擎、认证后端

* 🎨 主题插件化：`themes/<key>/theme.json` + `OA_THEME`，重启生效；登录页 SSO / 忘记密码占位入口 + 首屏加载动画

* 🌐 全站 UI 中英切换：插件名 / 表头 / 状态 / 空态 / 确认文案随语言切换（用户名与业务数据除外）

* 👤 个人中心：顶栏用户名可点击；编辑资料 / 查看权限 / 修改密码进入二级页面；用户编辑支持直接权限，且只展示操作者可授予的范围

* 📋 审批中心：请假 / 报销 / 用章 / 外出 / 加班 / 调休六类动态表单，必填标注、直属上级自动指派与抄送

* 📢 公告通知：发布 / 置顶 / 已读统计

* 🕐 考勤打卡：内勤 / 外勤签到、签到详情（时间范围 / 状态 / 类型筛选）、补卡登记、月度统计

* 🏠 工作台：待办聚合 + 流程快捷发起 + 公告简报，管理员 / 员工视图分流，侧栏当前 Tab 高亮

* ⛓ 区块链留痕：关键操作上链（SHA-256 哈希链），列表可点击查看单条记录详情，篡改即断链报警

* ⚙ 插件开关：工作台运行时启用 / 禁用插件，即时生效（停用即隐藏菜单 + 404），操作上链

* 🏢 组织增强：部门软删（即时 + 上链）/ 修改 / 硬删（会签审批全通过后物理删除 + 上链）

* 👤 用户状态机：启用 / 禁用（admin 直接禁用，普通管理员走会签）/ 冻结权限（即时短路），密码二次确认，超管权限层级最高

* ◫ 组织架构模板：职能制部门树 + 31 角色 + 31 用户模板一键幂等应用；组织关系树（责任划分）按直属上级归并，应用动作上链

* 🔐 RBAC 权限：权限码按 L0–L3 分级，角色按模板授予权限；拥有对应权限才能使用对应插件，菜单与 URL 同一口径

* 🧾 全员基线：考勤打卡与公告浏览登录即用；管理岗额外拥有签到详情（`attendance_report_view`）

* 🐳 Docker 一键部署：`docker compose up -d`（MySQL8 + Gunicorn + WhiteNoise，跨平台）

## 🛠 技术栈

Python 3.13・Django 5.2 LTS・MySQL 8.0（可切 sqlite）・Corporate Clean 企业简洁风（默认）/ Risograph（备选）・ECharts 5・Gunicorn・WhiteNoise・Docker Compose

## 🚀 快速开始

### Docker 一键部署（推荐）

跨平台：**Windows / macOS / Linux** 通用，仅需安装 Docker（Desktop 或 Engine），一条命令拉起。



```
docker compose up -d --build
# 访问 http://localhost:8000
# 默认超管：admin / Constellatio@2026（可用 .env 覆盖，见 .env.example）
```

### 本地开发



```
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
├── docker-compose.yml   # 一键部署（MySQL8 + web）
├── Dockerfile           # 应用镜像（gunicorn + whitenoise）
├── entrypoint.sh        # 容器启动脚本（migrate/collectstatic/超管/gunicorn）
├── .env.example         # 部署环境变量示例
├── .dockerignore
├── .gitattributes       # 行尾 LF 固定（容器执行必需）
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
├── themes/               # 主题插件层（可插拔，theme.json 发现）
│   ├── corporate-clean/  # 企业简洁风（默认）
│   └── risograph/        # Risograph 印刷风（备选）
├── locale/               # 翻译目录（.mo 由脚本编译，不入库）
├── tools/                # 纯 Python .mo 编译器
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



| 文档                                                                             | 类型   | 内容                                            |
| ------------------------------------------------------------------------------ | ---- | --------------------------------------------- |
| [README.md](README.md)（本文件）                                                    | 总览   | 项目入口、特性、快速开始                                  |
| [docs/tech-stack-and-architecture.md](docs/tech-stack-and-architecture.md)     | 设计   | 技术选型、全栈插件化架构、插件契约、竞品调研                        |
| [docs/constraints-and-acceptance.md](docs/constraints-and-acceptance.md)       | 规范   | 硬约束、功能边界、验收标准、开发规范、风险                         |
| [docs/database-design.md](docs/database-design.md)                             | 设计   | 数据库设计（插件化：每插件独立表与迁移）                          |
| [docs/development-guide.md](docs/development-guide.md)                         | 开发   | 开发流程、环境、容器实现、插件开发、编程规约、插件规范                   |
| [docs/ai-assisted-development-guide.md](docs/ai-assisted-development-guide.md) | 规范   | AI 辅助开发行为规范、迭代规范                              |
| [docs/project-overview.md](docs/project-overview.md)                           | 说明   | 项目说明、使用指南、插件开发示例                              |
| [docs/plugin-dev-workspace.md](docs/plugin-dev-workspace.md)                   | 插件开发 | workspace：工作台可启用 / 禁用功能（v1.1 已实现）             |
| [docs/plugin-dev-user.md](docs/plugin-dev-user.md)                             | 插件开发 | user 增强：部门软 / 硬删除、用户状态机、密码二次确认、权限层级（v1.2 已实现） |
| [docs/plugin-dev-structure.md](docs/plugin-dev-structure.md)                   | 插件开发 | structure：职能制组织架构模板（角色 + 用户模板一键应用）（v1.3 已实现）  |
| [docs/plugin-dev-language.md](docs/plugin-dev-language.md)                     | 插件开发 | language：语言切换（v1.4 已实现，v1.5.1 全站文案补全，v1.5.7 插件化 / 可停用）   |
| [docs/plugin-dev-theme.md](docs/plugin-dev-theme.md)                           | 插件开发 | theme：主题插件化 + Corporate Clean 默认主题（v1.5 已实现）   |
| [docs/plugin-dev-rbac.md](docs/plugin-dev-rbac.md)                             | 插件开发 | RBAC：权限等级 L0–L3、全员基线、角色权限模板、插件准入（v1.5.4 已实现） |
| [docs/plugin-dev-v155.md](docs/plugin-dev-v155.md)                             | 插件开发 | v1.5.5：审批动态表单 / 抄送、签到筛选 / 补卡、工作台、菜单高亮、密码权限 |
| [docs/plugin-dev-v156.md](docs/plugin-dev-v156.md)                             | 插件开发 | v1.5.6：组织关系树（责任划分）、责任人清单、汇报环 / 停用标记 |
| [docs/plugin-dev-v157.md](docs/plugin-dev-v157.md)                             | 插件开发 | v1.5.7：语言插件化 / 可停用、开关式插件 UI、plugin_switch 兜底命令 |
| [docs/plugin-dev-v158.md](docs/plugin-dev-v158.md)                             | 插件开发 | v1.5.8：功能区主题切换（运行时换肤，Cookie + ThemeLoader） |
| [docs/plugin-dev-v159.md](docs/plugin-dev-v159.md)                             | 插件开发 | v1.5.9：组织架构合并（当前架构 + 模板详情页 / 应用模板） |
| [docs/plugin-dev-v1510.md](docs/plugin-dev-v1510.md)                           | 插件开发 | v1.5.10：角色卡片点击弹窗（成员明细）+ 角色列表滚动自适应 |
| [docs/roadmap.md](docs/roadmap.md)                                             | 规划   | 差距矩阵、v1.5–v2.0 迭代路线、修复项与文档债务                  |

## 📌 状态

**v1.5.10 已跑通**（组织架构角色卡片可点击弹窗展示成员 / 角色列表限高滚动自适应 / 164 项测试全绿）→ 下一步：v1.6 图表插件化 + ECharts