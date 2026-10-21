# 开发指南

> 项目：Constellatio —— 基于 Django 的企业办公自动化系统（全栈插件化）
> 适用对象：项目开发人员
> 文档版本：v1.0 · 2026-10-21
> 前置阅读：tech-stack-and-architecture.md、constraints-and-acceptance.md

---

## 〇、开发流程总览（先看这节）

### 开发主线（串行依赖：容器 → 基础插件 → 业务插件 → 整合）

| 阶段 | 内容 | 验收门 |
|---|---|---|
| 0 环境 | Python / MySQL / Docker 安装 + `git init` | 空 Django 工程能启动 |
| 1 容器 | plugin_host：registry / discover / signals / 统一外壳 | 登录页可访问 |
| 2 auth+user | 登录插件 + 部门/角色/RBAC 插件 | 建角色、分配权限、越权拦截 |
| 3 approval | 审批状态机 + 审批留痕 | 发起→审批→归档闭环跑通 |
| 4 notice | 公告发布 / 置顶 / 已读 | 已读统计正确 |
| 5 attendance | 打卡防重 + 月度统计看板（ECharts） | 看板数据与打卡记录一致 |
| 6 整合 | Docker Compose 部署 + 可插拔三项验证 | 演示全部通过 |
| 7 测试发布 | 单元测试 + 测试报告 + 发布上线 | 验收标准全过 |

### 每阶段开发循环（一次 commit）

```
写 models → makemigrations/migrate → 写 services/views → 写模板 → 手动验证 → git commit
```

### Git 提交流程

- 每阶段一个 commit：`feat(plugin_host)` / `feat(user)` / `feat(approval)` / `feat(notice)` / `feat(attendance)` / `feat(deploy)`
- 完成一阶段打 tag：`v0.1`（容器）→ `v0.2`（auth+user）→ `v0.3`（approval）→ `v0.4`（notice）→ `v0.5`（attendance）→ `v1.0`（整合完成）

### 关键依赖规则

- user 插件是地基：必须最先完成（approval/notice/attendance 都要引用用户模型）
- 插件间交互只走 signals，禁止直接 import 对方模型
- 每阶段结束做"可插拔自检"：停掉刚完成的插件，确认系统照常跑、导航消失

---

## 一、开发环境搭建

### 1.1 安装清单

| 软件 | 版本 | 用途 |
|---|---|---|
| Python | 3.11+ | 运行时 |
| MySQL | 8.0 | 默认数据库（本机小皮面板已装） |
| Docker（Desktop/Engine） | 最新 | 一键部署，Windows/macOS/Linux 通用 |
| Git | 最新 | 版本管理 |
| 编辑器 | VS Code / PyCharm | 开发 |

### 1.2 初始化项目

```bash
# 1. 创建虚拟环境
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# 2. 安装 Django
pip install django==5.2.* mysqlclient gunicorn

# 3. 创建工程（根目录）
django-admin startproject plugin_host .

# 4. 创建业务插件目录结构
mkdir plugins
python manage.py startapp auth plugins\auth      # 依次创建各插件
python manage.py startapp user plugins\user
python manage.py startapp approval plugins\approval
python manage.py startapp notice plugins\notice
python manage.py startapp attendance plugins\attendance
```

### 1.3 依赖清单 requirements.txt

```
django==5.2.*
mysqlclient
gunicorn
```

## 二、插件容器 plugin_host 实现

容器是唯一固定核心，只做 5 件事：**注册 / 发现 / 外壳 / 信号 / 配置**。

### 2.1 插件注册表 registry.py

```python
# plugin_host/registry.py
"""插件注册表：OA_PLUGINS 配置驱动，运行时聚合插件元信息。"""

PLUGIN_REGISTRY = {}  # name -> PluginMeta


class PluginMeta:
    """插件契约：每个插件必须提供这些字段。"""

    def __init__(self, name, version, menus, permissions,
                 urls, signals, templates, app):
        self.name = name
        self.version = version
        self.menus = menus          # [{'label','icon','url'}, ...]
        self.permissions = []       # ['user_manage', 'approval_approve', ...]
        self.urls = urls            # 路由模块路径
        self.signals = signals      # 订阅/发出的信号
        self.templates = templates  # 模板目录
        self.app = app              # Django AppConfig 实例


def register(meta: PluginMeta):
    if meta.name in PLUGIN_REGISTRY:
        raise ValueError(f'插件重名: {meta.name}')
    PLUGIN_REGISTRY[meta.name] = meta


def get_plugins():
    """返回所有已启用插件（按 OA_PLUGINS 顺序）。"""
    return PLUGIN_REGISTRY


def get_menus(user):
    """按用户权限过滤菜单，容器外壳渲染用。"""
    from django.contrib.auth.models import Permission
    menus = []
    for meta in PLUGIN_REGISTRY.values():
        for menu in meta.menus:
            if _user_has_perm(user, meta, menu):
                menus.append({**menu, 'plugin': meta.name})
    return menus
```

### 2.2 自动发现 discover.py

```python
# plugin_host/discover.py
"""利用 Django AppConfig.ready() 自动扫描并注册插件。"""
from django.apps import AppConfig


class PluginHostConfig(AppConfig):
    name = 'plugin_host'

    def ready(self):
        # Django 会为每个 INSTALLED_APPS 调 AppConfig.ready()，
        # 各插件的 AppConfig 在自己的 ready() 中调用 registry.register(...)。
        # 此处只做已注册插件的校验与冲突检查。
        from .registry import PLUGIN_REGISTRY
        _check_permission_conflict(PLUGIN_REGISTRY)


def _check_permission_conflict(registry):
    seen = set()
    for meta in registry.values():
        for perm in meta.permissions:
            if perm in seen:
                raise ValueError(f'权限码冲突: {perm}')
            seen.add(perm)
```

### 2.3 统一外壳（登录 / 导航 / 布局）

```
plugin_host/templates/base.html   # 全局基座：侧边栏(动态菜单) + 顶栏 + 内容区
plugin_host/templates/login.html  # 统一登录页
```

基座要点：

```html
<!-- base.html 关键部分：动态导航由 get_menus(request.user) 渲染 -->
<aside>
  {% for menu in menus %}
    <a href="{{ menu.url }}" class="nav-item">
      <span>{{ menu.icon }}</span> {{ menu.label }}
    </a>
  {% endfor %}
</aside>
<main>{% block content %}{% endblock %}</main>
```

### 2.4 信号总线 signals.py

```python
# plugin_host/signals.py
"""插件间通信总线：跨插件交互一律走信号，禁止直接 import 对方模型。"""
from django.dispatch import Signal

# 定义全局业务信号
approval_finished = Signal()      # 审批结束（发起/通过/驳回），携带 approval_id, result
notice_published = Signal()       # 公告发布，携带 announcement_id
attendance_checked = Signal()     # 打卡成功，携带 user_id, date
```

## 三、插件开发规范（以 approval 为例）

### 3.1 插件目录结构

```
plugins/approval/
├── apps.py            # AppConfig + 插件契约声明（核心）
├── models.py          # approval / approval_record
├── views.py           # 业务视图
├── urls.py            # 路由，挂载 /plugins/approval/
├── admin.py           # 后台管理
├── migrations/
├── templates/approval/  # 模板片段（继承 base.html）
└── signals.py         # 本插件信号处理
```

### 3.2 插件契约声明 apps.py

```python
# plugins/approval/apps.py
from django.apps import AppConfig
from plugin_host.registry import register, PluginMeta


class ApprovalPluginConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'plugins.approval'
    label = 'approval'

    def ready(self):
        from plugin_host import signals as bus
        from . import signals  # noqa: 确保信号处理函数注册
        register(PluginMeta(
            name='approval',
            version='1.0.0',
            menus=[
                {'label': '审批中心', 'icon': '📋', 'url': '/plugins/approval/'},
                {'label': '我的待办', 'icon': '✅', 'url': '/plugins/approval/todo/'},
                {'label': '我的申请', 'icon': '📤', 'url': '/plugins/approval/mine/'},
            ],
            permissions=[
                'approval_submit',    # 发起审批
                'approval_approve',   # 审批他人
                'approval_manage',    # 管理全部
            ],
            urls='plugins.approval.urls',
            signals=[bus.approval_finished],
            templates='approval',
            app=self,
        ))
```

### 3.3 审批状态机 models.py

```python
# plugins/approval/models.py
from django.db import models
from django.conf import settings

APPROVAL_TYPES = (('leave', '请假'), ('reimburse', '报销'), ('stamp', '用章'))

# 状态机：draft -> pending -> approved / rejected
STATUS_CHOICES = (
    ('draft', '草稿'), ('pending', '审批中'),
    ('approved', '已通过'), ('rejected', '已驳回'),
)


class Approval(models.Model):
    type = models.CharField(max_length=20, choices=APPROVAL_TYPES)
    title = models.CharField(max_length=200)
    content = models.TextField()                  # 申请内容
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                  related_name='approvals')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    current_approver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='pending_approvals')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ApprovalRecord(models.Model):
    """审批留痕：谁、什么动作、什么意见、什么时候。"""
    approval = models.ForeignKey(Approval, on_delete=models.CASCADE, related_name='records')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=20, choices=(('submit', '提交'), ('approve', '通过'), ('reject', '驳回')))
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 3.4 状态机流转逻辑（放 services 层，保证可单测）

```python
# plugins/approval/services.py
from .models import Approval, ApprovalRecord
from plugin_host.signals import approval_finished


def submit(approval: Approval, user):
    approval.status = 'pending'
    approval.current_approver = _next_approver(approval)  # 部门主管/角色
    approval.save()
    ApprovalRecord.objects.create(approval=approval, approver=user, action='submit')


def approve(approval: Approval, user, comment=''):
    approval.status = 'approved'
    approval.current_approver = None
    approval.save()
    ApprovalRecord.objects.create(approval=approval, approver=user, action='approve', comment=comment)
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='approved')


def reject(approval: Approval, user, comment):
    approval.status = 'rejected'
    approval.current_approver = None
    approval.save()
    ApprovalRecord.objects.create(approval=approval, approver=user, action='reject', comment=comment)
    approval_finished.send(sender=approval.__class__, approval_id=approval.id, result='rejected')
```

> 状态机规则：只有 `pending` 才能 approve/reject；只有 `draft/pending` 能 submit。
> 所有流转必须落 ApprovalRecord，保证"全程留痕"可追溯。

## 四、各业务插件开发要点

### 4.1 auth 插件（认证）

```python
# plugins/auth/views.py —— 登录视图
from django.contrib.auth import authenticate, login

def login_view(request):
    if request.method == 'POST':
        user = authenticate(request,
                            username=request.POST['username'],
                            password=request.POST['password'])
        if user:
            login(request, user)
            return redirect('index')
    return render(request, 'auth/login.html')
```

- 认证后端可插拔：`AUTHENTICATION_BACKENDS` 加一行即可扩展 LDAP/OAuth

### 4.2 user 插件（RBAC 地基）

```python
# plugins/user/models.py
from django.contrib.auth.models import AbstractUser


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    permissions = models.ManyToManyField('auth.Permission')   # 角色挂权限


class User(AbstractUser):
    """扩展用户：部门 + 角色。"""
    department = models.ForeignKey(Department, null=True, on_delete=models.SET_NULL)
    roles = models.ManyToManyField(Role)
```

- **必须**在 settings.py 设置 `AUTH_USER_MODEL = 'user.User'`，且在首次 migrate 前配置
- 视图装饰器：`@login_required` + `@permission_required('approval_approve')`

### 4.3 notice 插件（公告 + 已读）

```python
# plugins/notice/models.py
class Announcement(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    publisher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    is_top = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('announcement', 'user')   # 一人一篇只记一次
```

- 已读统计：`AnnouncementRead.objects.filter(announcement=a).count()`
- 未读数 = 用户可看公告数 - 已读数

### 4.4 attendance 插件（考勤 + 统计）

```python
# plugins/attendance/models.py
class Attendance(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'date')   # 一天一卡，防重复打卡
```

- 打卡接口：`check_in` 为空则记上班，已存在则记下班（`unique_together` 防重）
- 月度统计：按 `date__year/month` 聚合，数据源喂给 ECharts：

```python
# plugins/attendance/views.py —— 统计接口返回 JSON
def monthly_stats(request):
    rows = (Attendance.objects
            .filter(user=request.user, date__year=..., date__month=...)
            .order_by('date'))
    data = {
        'dates': [a.date.strftime('%m-%d') for a in rows],
        'hours': [calc_hours(a) for a in rows],
    }
    return JsonResponse(data)   # 前端 ECharts 直接消费
```

## 五、前端开发规范

- 页面一律继承 `plugin_host/templates/base.html`，插件只写 `{% block content %}`
- UI 组件用 Bootstrap 5（栅格/卡片/表格/表单），禁止自造样式体系
- ECharts 通过 CDN 引入，图表统一封装：

```html
<!-- attendance/templates/attendance/stats.html 片段 -->
<div id="chart" style="width:100%;height:400px;"></div>
<script>
  fetch('/plugins/attendance/stats/')
    .then(r => r.json())
    .then(data => {
      const chart = echarts.init(document.getElementById('chart'));
      chart.setOption({
        xAxis: { type: 'category', data: data.dates },
        yAxis: { type: 'value' },
        series: [{ type: 'line', data: data.hours, smooth: true }]
      });
    });
</script>
```

## 六、数据库开发

### 6.1 默认 MySQL（生产环境）

```python
# plugin_host/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'oa_db',
        'USER': 'root',
        'PASSWORD': '你的密码',
        'HOST': '127.0.0.1',
        'PORT': '3306',
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
```

### 6.2 切换 sqlite（演示数据库可插拔）

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### 6.3 迁移流程

```bash
python manage.py makemigrations            # 生成全部插件迁移
python manage.py migrate                   # 应用迁移
python manage.py shell -c "from plugins.user.models import Role; Role.objects.create(name='管理员')"
```

## 七、测试

```python
# plugins/approval/tests.py —— 状态机单元测试（必写）
from django.test import TestCase
from plugins.approval.services import submit, approve, reject


class ApprovalFlowTest(TestCase):
    def test_approve_flow(self):
        a = Approval.objects.create(...)
        submit(a, applicant)          # draft -> pending
        self.assertEqual(a.status, 'pending')
        approve(a, approver)          # pending -> approved
        a.refresh_from_db()
        self.assertEqual(a.status, 'approved')
        self.assertEqual(a.records.count(), 2)   # 留痕完整

    def test_reject_from_approved_should_fail(self):
        # 非法流转应抛异常
        with self.assertRaises(ValueError):
            reject(approved_obj, user, 'x')
```

```bash
python manage.py test plugins
```

## 八、部署开发

### 8.1 Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
EXPOSE 8000
CMD ["gunicorn", "plugin_host.wsgi:application", "-b", "0.0.0.0:8000"]
```

### 8.2 docker-compose.yml

```yaml
services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: oa_db
      MYSQL_ROOT_PASSWORD: oa_pass
    volumes:
      - db_data:/var/lib/mysql
  web:
    build: .
    command: sh -c "python manage.py migrate && gunicorn plugin_host.wsgi:application -b 0.0.0.0:8000"
    depends_on: [db]
    ports: ["8000:8000"]
  nginx:
    image: nginx:latest
    ports: ["80:80"]
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
    depends_on: [web]
volumes:
  db_data:
```

## 九、Git 工作流

```bash
# 每完成一个插件/功能，一次提交
git init
git add .
git commit -m "feat(plugin_host): 插件注册表与自动发现"
git commit -m "feat(user): 部门/角色/RBAC 模型与视图"
git commit -m "feat(approval): 审批状态机与留痕"
git commit -m "feat(attendance): 打卡与月度统计看板"
git commit -m "docs: 补充开发指南"
```

## 十、常见问题排查

| 问题 | 原因 | 解决 |
|---|---|---|
| `AUTH_USER_MODEL` 报错 | 用户模型替换须在首次 migrate 前 | 项目初始化时先配好再 migrate |
| 插件停用后 URL 404 | 路由还挂在主 urls.py | 路由由注册表按 OA_PLUGINS 动态 include |
| 信号重复触发 | 信号函数幂等性不足 | 处理函数先查重再执行 |
| mysqlclient 装不上 | 缺编译环境 | Windows 用 `pip install mysqlclient` 或装预编译 wheel |
| 中文乱码 | 编码不一致 | 数据库 utf8mb4；文件 UTF-8 带 BOM |
| 权限码冲突 | 插件权限码重名 | 统一 `插件名_权限` 前缀，注册时校验 |

---

## 十一、编程规约

### 11.1 Python 规约

| 项 | 规约 |
|---|---|
| 风格 | PEP 8；行宽 ≤ 100 字符 |
| 命名 | 类 `UpperCamelCase`；函数/变量 `snake_case`；常量 `UPPER_SNAKE` |
| 类型 | 公共函数加类型注解；复杂返回值写清 docstring |
| 文档 | 模块级 docstring（用途）；函数 docstring（作用/参数/返回） |
| 异常 | 只捕获预期异常；禁止吞异常、禁止 `print` 调试残留，统一记日志 |
| 导入 | 分三组：标准库 → Django → 项目内；禁止 `from xxx import *` |

### 11.2 Django 规约

| 项 | 规约 |
|---|---|
| 分层 | MVT：models 只管数据、views/services 管业务、模板只渲染，禁止互相越权 |
| 查询 | 一律 ORM；**禁止 raw SQL / 字符串拼接 SQL** |
| 业务逻辑 | 复杂逻辑放 `services.py`（如 approval/services.py），views 不写大段逻辑 |
| 输入校验 | 用 Django Form / Serializer 校验，禁止手写 `request.POST` 裸拼装 |
| 视图 | 类视图优先（ListView/CreateView）；加 `@login_required` + 权限装饰器 |
| 迁移 | 改模型后必须 `makemigrations`；禁止手改数据库 |
| 信号 | 处理函数必须幂等；禁止在信号里做重 IO 操作 |
| 配置 | 敏感配置走环境变量 / `.env`；禁止硬编码密钥 |

### 11.3 插件规约（编码层）

| 项 | 规约 |
|---|---|
| 目录 | 每插件 `plugins/<name>/` 完整自包含（models/views/urls/templates/apps） |
| 引用 | 插件间**零 import**；只用 user 插件 API 或 signals |
| 路由 | 挂载 `/plugins/<name>/` 前缀；URL 命名空间用插件名 |
| 权限 | 权限码 `插件名_权限` 前缀；视图统一装饰器校验 |
| 启停 | 不动插件代码即插即拔；停用状态只走 `OA_PLUGINS` 配置 |

### 11.4 前端规约

| 项 | 规约 |
|---|---|
| 模板 | 只做渲染；禁止在 `{% %}` 里写业务逻辑或查询 |
| JS | 事件绑定用 `data-` 属性；禁止内联 `onclick` |
| 样式 | Bootstrap 类优先；自写 CSS 放插件 `static/`，类名前缀 `<插件名>-` |
| 图表 | ECharts 封装统一初始化函数，禁止到处重复 init |

### 11.5 数据库规约（编码层）

| 项 | 规约 |
|---|---|
| ORM | 禁 raw；批量操作用 `bulk_create` / `bulk_update` |
| 索引 | 常用查询字段加 `db_index`；联合查询建联合索引 |
| 删除 | 业务主数据 `PROTECT` / `SET_NULL`；记录类 `CASCADE` |
| 事务 | 多步写操作包 `transaction.atomic` |

### 11.6 安全规约

- 模板输出走 Django 默认自动转义；**禁止滥用 `|safe`**
- 表单一律带 CSRF；文件上传校验类型与大小
- 密码由框架哈希；日志禁止打印敏感字段（密码/Token/手机号）

### 11.7 通用规约

| 项 | 规约 |
|---|---|
| 日志 | `logging` 统一输出，禁 `print` |
| 配置 | 环境变量 / settings 常量集中管理，禁止散落魔法值 |
| 错误 | 用户可见错误友好提示，不泄露堆栈 |
| 提交 | 遵循 Git 规范（见"九、Git 工作流"） |

---

## 十二、插件规范（完整版）

### 12.1 插件生命周期

```
发现 → 注册 → 启用 → 运行 → 停用 → 卸载（可选）
```

| 阶段 | 触发方式 | 说明 |
|---|---|---|
| 发现 | Django 启动，`AppConfig.ready()` 自动调用 | 容器扫描 INSTALLED_APPS 中声明了插件契约的 app |
| 注册 | `registry.register(PluginMeta)` | 提交元信息，冲突校验（重名/权限码） |
| 启用/停用 | 只改 `OA_PLUGINS` 配置 | 导航/权限/路由自动收敛，不动代码 |
| 运行 | 请求路由 `/plugins/<name>/` | 插件独立处理 |
| 卸载 | 明确执行（默认不提供） | 停用只隐藏；卸载才删表，谨慎操作 |

### 12.2 插件元信息规范（PluginMeta 完整字段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | str | ✓ | 插件唯一名，小写英文，全局唯一 |
| version | str | ✓ | 语义化版本（SemVer） |
| menus | list[dict] | ✓ | 导航菜单：`{label, icon, url}` |
| permissions | list[str] | ✓ | 权限码，格式 `插件名_权限` |
| urls | str | ✓ | 路由模块路径 |
| signals | list | ✓ | 订阅/发出的信号 |
| templates | str | ✓ | 模板目录名 |
| app | AppConfig | ✓ | 自身 AppConfig 实例 |
| dependencies | list[str] | 可选 | 依赖的其他插件名（如 approval 依赖 user） |
| admin | bool | 可选 | 是否注册 Django Admin |

### 12.3 插件间通信规范

**只允许两种通信方式**：信号（signals）+ user 插件只读 API。禁止直接 import 对方模型、跨表 JOIN、写对方表。

全局信号总线（`plugin_host/signals.py`）：

| 信号 | 触发方 | 载荷 | 典型订阅方 |
|---|---|---|---|
| approval_finished | approval | approval_id, result | notice（消息通知） |
| notice_published | notice | announcement_id | — |
| attendance_checked | attendance | user_id, date | — |
| user_created / user_updated | user | user_id | 各插件同步 |

兼容规则：对外信号载荷**只增不改**；改字段须升插件主版本。

### 12.4 插件依赖与版本

- 依赖声明：`PluginMeta.dependencies = ['user']`
- 容器启动时校验依赖顺序：先加载被依赖插件，缺失则报错并禁止启用
- 插件版本独立 SemVer；升级不得破坏容器公共 API
- 权限码冲突、依赖环（A→B→A）由容器启动时拦截

### 12.5 插件测试规范

- 每插件独立 `tests.py`；测试用独立数据库（Django 默认隔离）
- 必测项：
  - [ ] 模型约束（UNIQUE 防重）
  - [ ] 状态机流转（审批 submit/approve/reject 合法与非法路径）
  - [ ] 权限拦截（无权限角色访问被拒）
  - [ ] 插件停用后系统照常运行（可插拔自检）
- 运行：`python manage.py test <插件名>`

### 12.6 插件文档要求

每个插件必须自述：功能、依赖、权限码、信号、配置项（写在插件 `README.md` 或模块 docstring）。

新插件验收清单（全部满足才可合入）：

- [ ] PluginMeta 字段完整（12.2 表格全 ✓）
- [ ] 独立 migrations，可单独建表
- [ ] 权限码带 `插件名_` 前缀且无冲突
- [ ] 停用后可插拔自检通过
- [ ] 有单元测试且通过
- [ ] 文档齐全（功能/依赖/信号/权限）
