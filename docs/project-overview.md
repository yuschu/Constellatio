# 项目说明文档

> 项目代号：**Constellatio**
> 系统名称：基于 Django 的企业办公自动化系统（OA）
> 设计思想：**万物皆可插件**（全栈插件化）
> 文档版本：v1.9 · 2026-10-22（v1.5 主题插件化完成）

---

## 一、项目简介

本系统是面向中小企业与高校的轻量级办公自动化（OA）系统，采用 Python + Django 实现。核心设计思想为"**万物皆可插件**"：系统由一个固定插件容器（plugin_host）与若干可插拔插件组成，从数据库、模板、图表等基础设施到审批、公告、考勤等业务模块，全部支持独立启停、替换与扩展。

相比飞书、钉钉等商业 SaaS（贵、数据上云）与泛微、蓝凌等传统厂商（技术栈旧、实施周期长），本系统以轻量、免费、可私有化、按需定制为定位，填补中小企业/高校轻量自建 OA 的空白。

## 二、设计思想

```
万物皆可插件：
┌─ 业务插件层 ─ auth / user / approval / notice / attendance / blockchain / workspace / structure / language / sso / notify ─┐
│ 基础设施插件层 ─ DB后端 / 模板引擎 / 主题UI / 图表引擎 / 认证（SSO） │
│ 插件容器 plugin_host（唯一固定：注册表/外壳/信号/配置）        │
└─ 部署：WhiteNoise + Gunicorn + Django + MySQL（Docker Compose）  ─┘
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
| blockchain | 操作留痕上链 | 订阅全局信号写入哈希链，列表可点击查看记录详情，篡改即断链报警 |
| workspace | 插件开关 | 运行时启用 / 停用，停用即 404 + 菜单隐藏（v1.1） |
| structure | 组织架构模板 | 20 部门 / 31 角色 / 31 用户幂等应用（v1.3） |
| language | 中英切换 | 默认中文 + 会话 Cookie + 全站 UI 文案中英切换（v1.5.1） |
| theme | 主题插件 | Corporate Clean 默认 / Risograph 备选，`OA_THEME` 切换（v1.5） |
| sso | 企业单点登录 | HMAC 签名 Ticket 网关登录、自动建号、防重放、登录页入口（v1.7.0） |
| notify | 消息提醒 | 站内信：审批待办 / 结果、公告发布、顶栏未读、消息中心、工作台卡片（v1.7.0） |

## 四、技术栈

- Python 3.13 / Django 5.2 LTS / MySQL 8.0
- Django 模板 + Corporate Clean 企业简洁风（默认）/ Risograph（备选）+ ECharts 5
- Gunicorn + WhiteNoise + Docker Compose（跨平台一键部署）

## 五、快速开始

### 方式一：Docker 一键部署（推荐）

跨平台：**Windows / macOS / Linux** 通用，仅需安装 Docker，一条命令拉起。

```bash
docker compose up -d --build
# 访问 http://localhost:8000 （默认超管 admin / Constellatio@2026）
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

## 六、目录结构（v1.0 已落地）

```
Constellatio/
├── docker-compose.yml          # 一键部署（MySQL8 + web，已实现）
├── Dockerfile                  # 应用镜像（gunicorn + whitenoise，已实现）
├── entrypoint.sh               # 容器启动脚本（migrate/collectstatic/超管/gunicorn，已实现）
├── .env.example                # 部署环境变量示例
├── .dockerignore / .gitattributes
├── requirements.txt
├── manage.py
├── plugin_host/                # 插件容器（唯一固定核心，已实现）
│   ├── registry.py             # 插件注册表（PluginMeta / 菜单聚合）
│   ├── discover.py             # 自动发现与注册校验
│   ├── signals.py              # 信号总线
│   ├── context_processors.py   # 模板注入聚合菜单
│   ├── views.py                # 工作台首页
│   ├── apps.py                 # 容器 AppConfig
│   ├── settings.py             # 全局配置（OA_PLUGINS / OA_THEME / AUTH_USER_MODEL）
│   └── urls.py                 # 插件路由动态聚合
├── plugins/                    # 业务插件（全部可插拔）
│   ├── auth/                   # 认证插件（登录/登出，已实现）
│   ├── user/                   # 用户/部门/角色/RBAC 插件（已实现 v0.2）
│   ├── approval/               # 审批中心插件（已实现 v0.3）
│   ├── notice/                 # 公告通知插件（已实现 v0.4）
│   ├── attendance/             # 考勤打卡插件（已实现 v0.5）
│   ├── blockchain/             # 操作留痕上链插件（已实现 v0.6）
│   ├── workspace/              # 运行时插件开关（v1.1）
│   ├── structure/              # 组织架构模板（v1.3）
│   ├── language/               # 中英切换（v1.4）
│   ├── sso/                    # 企业 SSO 签名 Ticket 登录（v1.7.0）
│   └── notify/                 # 站内消息提醒（v1.7.0）
├── themes/                     # 主题插件层（可插拔，theme.json 发现）
│   ├── corporate-clean/        # 企业简洁风（默认）
│   └── risograph/              # Risograph 印刷风（备选）
└── docs/                       # 文档
    ├── tech-stack-and-architecture.md
    ├── constraints-and-acceptance.md
    ├── project-overview.md
    ├── development-guide.md
    ├── ai-assisted-development-guide.md
    └── database-design.md
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

- [x] 插件容器 v0.1（登录页可访问 / 外壳渲染 / 菜单聚合）—— 2026-10-21 完成
- [x] RBAC v0.2（部门/用户/角色管理 + 菜单/视图权限过滤 + user_created/updated 信号）—— 2026-10-21 完成
- [x] 审批中心 v0.3（请假/报销/用章，状态机 + 全程留痕 + approval_finished 信号 + 5 项单测）—— 2026-10-21 完成
- [x] 公告中心 v0.4（置顶排序 + 未读徽标 + 已读幂等统计 + notice_published 信号 + 3 项单测）—— 2026-10-21 完成
- [x] 考勤打卡 v0.5（一天一卡 + 本月出勤/迟到统计 + attendance_checked 信号 + 3 项单测）—— 2026-10-21 完成
- [x] 留痕链 v0.6（SHA256 哈希链 + 5 信号自动上链 + 篡改检测 + 4 项单测）—— 2026-10-21 完成
- [ ] 需求规格说明书
- [x] 数据库设计文档（ER 图）—— 已完成：`docs/database-design.md`
- [x] 整合部署 v1.0（Docker Compose：MySQL8 + Gunicorn + WhiteNoise）—— 2026-10-21 完成并冒烟通过
- [x] v1.1 workspace 插件（工作台可启用/禁用功能，运行时开关，停用即 404+菜单隐藏，操作上链）—— 2026-10-21 完成：`docs/plugin-dev-workspace.md`
- [x] v1.2 user 增强 + approval 会签（部门软/硬删+修改、用户状态机、密码二次确认、权限层级；会签模型）—— 2026-10-21 完成：`docs/plugin-dev-user.md`
- [x] v1.3 structure 插件（职能制组织架构模板：20 部门/31 角色/31 用户模板幂等应用，应用上链）—— 2026-10-21 完成：`docs/plugin-dev-structure.md`
- [x] v1.4 language 插件（默认中英文切换，13 项单测 + 双语冒烟）—— 2026-10-22 完成：`docs/plugin-dev-language.md`
- [x] v1.5 theme 插件（Corporate Clean 默认 / Risograph 备选 + 登录占位入口 + 首屏 loader）—— 2026-10-22 完成：`docs/plugin-dev-theme.md`
- [x] v1.5.1 全站 UI 文案中英补全（插件名 / 表头 / 状态 / 空态 / confirm）+ 留痕记录点击查看详情—— 2026-10-22
- [x] v1.5.2 留痕链插件/动作展示名本地化—— 2026-10-22
- [x] v1.6 图表插件化（ChartRenderer Provider + ECharts 本地资源 + 考勤月度看板）—— 2026-10-23：`docs/plugin-dev-v16.md`
- [x] v1.6.1–v1.6.20 图表开关 / 工作台大盘 / 公告合并 / 页面统一（237 项测试，tag `v1.6.20`）—— 2026-10-24
- [x] v1.7.0 企业 SSO（签名 Ticket）+ 消息提醒站内信（259 项测试）—— 2026-10-24：`docs/plugin-dev-sso.md`、`docs/plugin-dev-notify.md`
- [x] v1.7.1 安全与并发修复包（行锁与事务 / 对象级鉴权 / 传输安全 / 登录限流 / 注册表系统检查 / 分页与缓存 / ruff + CI，323 项测试，tag `v1.7.1`）—— 2026-10-27：`docs/plugin-dev-v171.md`
- [x] v1.7.2 公告极简化（单列公告流 / 自动已读 / 已读明细页）+ 考勤规则（上下班/宽限/工作日/补卡回溯，规则设置页，352 项测试，tag `v1.7.2`）—— 2026-10-27：`docs/plugin-dev-v172.md`
- [x] v1.5.3 个人中心（资料 / 权限 / 改密）、用户编辑权限范围、登录回填用户名、公告对所有登录用户可见（76 项测试全绿）—— 2026-10-22
- [x] v1.5.4 权限等级 L0–L3、全员基线（考勤/公告）、角色模板权限、插件准入统一守卫、管理岗签到详情（102 项测试全绿）—— 2026-10-22
- [x] v1.5.5 审批六类动态表单 + 直属上级抄送、签到状态/类型/时间筛选与补卡、工作台双视图、侧栏高亮、密码权限（138 项测试全绿）—— 2026-10-22
- [ ] 测试报告
