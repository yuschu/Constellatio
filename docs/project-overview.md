# 项目说明文档

> 项目代号：**Constellatio**
> 系统名称：基于 Django 的企业办公自动化系统（OA）
> 设计思想：**万物皆可插件**（全栈插件化）
> 文档版本：v1.1 · 2026-10-21

---

## 一、项目简介

本系统是面向中小企业与高校的轻量级办公自动化（OA）系统，采用 Python + Django 实现。核心设计思想为"**万物皆可插件**"：系统由一个固定插件容器（plugin_host）与若干可插拔插件组成，从数据库、模板、图表等基础设施到审批、公告、考勤等业务模块，全部支持独立启停、替换与扩展。

相比飞书、钉钉等商业 SaaS（贵、数据上云）与泛微、蓝凌等传统厂商（技术栈旧、实施周期长），本系统以轻量、免费、可私有化、按需定制为定位，填补中小企业/高校轻量自建 OA 的空白。

## 二、设计思想

```
万物皆可插件：
┌─ 业务插件层 ─ auth / user / approval / notice / attendance / blockchain ─┐
│ 基础设施插件层 ─ DB后端 / 模板引擎 / 主题UI / 图表引擎 / 认证 │
│ 插件容器 plugin_host（唯一固定：注册表/外壳/信号/配置）        │
└─ 部署：Nginx + Gunicorn + Django + MySQL（Docker Compose）  ─┘
```

核心原则：
1. 容器唯一固定，业务全插件化，无"不可拔业务模块"
2. 插件只通过 PluginMeta 声明 + signals 通信，互不 import
3. 启停只改配置（`OA_PLUGINS`），系统自动收敛导航/权限/路由

## 三、功能列表

| 插件 | 功能 | 说明 |
|---|---|---|
| auth | 登录/登出/会话 | 认证后端可插拔（默认 session） |
| user | 部门/用户/角色/RBAC | 权限体系地基，被所有插件引用 |
| approval | 审批中心 | 请假/报销/用章，状态机 + 审批留痕 |
| notice | 公告通知 | 发布/置顶/已读统计 |
| attendance | 考勤打卡 | 上下班打卡 + 月度统计看板（ECharts） |
| blockchain | 操作留痕上链 | 订阅全局信号写入哈希链，篡改即断链报警 |

## 四、技术栈

- Python 3.11+ / Django 5.2 LTS / MySQL 8.0
- Django 模板 + Bootstrap 5 + ECharts 5
- Gunicorn + Nginx + Docker Compose

## 五、快速开始

### 方式一：Docker 一键部署（推荐）

跨平台：**Windows / macOS / Linux** 通用，仅需安装 Docker，一条命令拉起。

```bash
docker compose up -d
# 访问 http://localhost:80
```

### 方式二：本地开发

```bash
# 1. 建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 2. 配置数据库（.env 中设置 MySQL 连接，或默认 sqlite）

# 3. 迁移 + 初始化
python manage.py migrate
python manage.py createsuperuser

# 4. 启动
python manage.py runserver
```

## 六、目录结构（规划）

```
Constellatio/
├── docker-compose.yml          # 一键部署
├── Dockerfile
├── nginx/                      # Nginx 配置
├── requirements.txt
├── manage.py
├── plugin_host/                # 插件容器（唯一固定核心）
│   ├── registry.py             # 插件注册表
│   ├── discover.py             # 自动发现（AppConfig.ready）
│   ├── shell/                  # 统一外壳（登录/导航/布局）
│   └── signals.py              # 信号总线
├── plugins/                    # 业务插件（全部可插拔）
│   ├── auth/                   # 认证插件
│   ├── user/                   # 用户/部门/角色/RBAC 插件
│   ├── approval/               # 审批中心插件
│   ├── notice/                 # 公告通知插件
│   ├── attendance/             # 考勤打卡插件
│   └── blockchain/             # 操作留痕上链插件
└── docs/                       # 文档
    ├── tech-stack-and-architecture.md
    ├── constraints-and-acceptance.md
    ├── project-overview.md
    └── development-guide.md
```

## 七、如何开发一个插件（即插即用示例）

以"会议室预约"插件为例：

1. 创建插件目录 `plugins/meeting/`，包含 `models.py`、`views.py`、`urls.py`、`templates/`、`apps.py`
2. 在 `apps.py` 中声明 PluginMeta：

```python
class MeetingPluginConfig(AppConfig):
    name = 'plugins.meeting'
    plugin_meta = {
        'name': '会议室预约',
        'version': '1.0.0',
        'menus': [{'label': '会议室预约', 'icon': '🏢', 'url': '/plugins/meeting/'}],
        'permissions': ['meeting_book', 'meeting_manage'],
        'urls': 'plugins.meeting.urls',
        'signals': [],
    }
```

3. 在 `OA_PLUGINS` 中加一行启用：

```python
OA_PLUGINS = [
    {'app': 'plugins.meeting', 'enabled': True},
]
```

4. 重启后容器自动发现：菜单出现、权限并入 RBAC、路由挂载完成——**即插即用**

## 八、文档索引

| 文档 | 路径 | 内容 |
|---|---|---|
| 技术栈与架构方案 | `docs/tech-stack-and-architecture.md` | 技术选型、架构设计、插件契约、竞品调研、排期 |
| 约束与验收规范 | `docs/constraints-and-acceptance.md` | 硬约束、功能边界、验收标准、开发规范、风险 |
| 项目说明文档 | `docs/project-overview.md` | 本项目文件（当前） |
| 开发指南 | `docs/development-guide.md` | 环境搭建、容器实现、插件开发、部署、测试 |
| AI 辅助开发规范 | `docs/ai-assisted-development-guide.md` | AI 辅助开发的行为规范与红线 |
| 数据库设计文档 | `docs/database-design.md` | 数据库设计（插件化：每插件独立表与迁移） |

## 九、待办（后续文档）

- [ ] 需求规格说明书
- [x] 数据库设计文档（ER 图）—— 已完成：`docs/database-design.md`
- [ ] 测试报告
