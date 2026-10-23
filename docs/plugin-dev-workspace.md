# 插件开发文档：workspace（工作台可启用/禁用功能）

> 关联插件：plugin_host 容器（registry 运行时开关）
> 版本规划：v1.1 · 文档版本：v1.1 · 2026-10-21
> 状态：**✅ 已实现并跑通**（4 项单测全绿 + HTTP 冒烟：停用即 404、菜单隐藏、启用恢复、plugin_toggled 上链、链校验通过）

## 一、需求

工作台新增"可启用/禁用功能"：在系统内（工作台入口）以开关形式**运行时**启用/停用各插件，无需改 `OA_PLUGINS` 配置、无需重启。操作即时生效、留痕上链。

## 二、设计要点

| 项 | 决策 |
|---|---|
| 形态 | 新插件 `plugins/workspace`（"万物皆可插件"：管理能力本身也是插件） |
| 运行时开关 | 新建表 `workspace_pluginswitch`（app_key, enabled）持久化，**DB 优先覆盖** settings.OA_PLUGINS 静态配置 |
| 生效机制 | `registry.get_enabled_plugins()` 改造：先读 DB 开关，无记录回退静态配置；菜单/权限收敛基于它 → 一次请求即生效；**路由即时生效**：新增 `plugin_host.middleware.PluginRouteGuardMiddleware`（URLConf 静态 include 无法按请求刷新，中间件对停用插件请求直接 404） |
| 防锁死 | v1.5.7 起禁停清单只剩 `workspace`（开关入口自身）；`auth / user / structure / language` 均可停用。停用 `auth` 后登录入口 404（已登录会话仍可用），用 `manage.py plugin_switch on auth` 兜底恢复 |
| 权限 | 新权限码 `workspace_manage`（普通管理员即可操作，即时生效） |
| 上链 | 开关操作发 `plugin_toggled` 信号 → blockchain 订阅上链 |
| 页面 | home 工作台新增"插件开关"入口卡片 → `/plugins/workspace/` 开关页（插件列表 + **开关（toggle）**） |

## 三、数据模型（plugins/workspace/models.py）

**workspace_pluginswitch（插件运行时开关）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | |
| app_key | VARCHAR(100) | UNIQUE, NOT NULL | 插件 key（= 注册名，如 `notice`） |
| enabled | BOOL | NOT NULL, DEFAULT True | 开关状态 |
| updated_by | FK user_user | NULL, SET_NULL | 最后操作人 |
| updated_at | DATETIME | auto_now | |

Meta：permissions = [('workspace_manage', '插件开关管理')]

## 四、接口 / 路由

| 路由 | 视图 | 说明 |
|---|---|---|
| `/plugins/workspace/` | switch_list | 列出全部已注册插件 + 当前开关状态（登录 + workspace_manage） |
| `/plugins/workspace/<app_key>/toggle/` | switch_toggle | POST；只拦截 `workspace`（v1.5.7，其余插件均可停用）；写 DB → 发 `plugin_toggled` → 上链；返回列表页 |

## 五、信号与上链

1. plugin_host/signals.py 新增：`plugin_toggled = Signal()`（携带 app_key, enabled, operator_id）
2. workspace 视图 toggle 后 send；blockchain apps.ready 增订阅 → `BlockchainRecord.append(plugin='workspace', action='plugin_toggled', payload=f'{app_key}:{enabled}', operator=...)`
3. `registry.get_enabled_plugins()` 改造（DB 优先）：

```python
def get_enabled_plugins():
    """OA_PLUGINS 静态配置 + workspace 运行时开关（DB 覆盖，缺表/记录时回退静态）。"""
    try:
        from plugins.workspace.models import PluginSwitch
        switches = {s.app_key: s.enabled for s in PluginSwitch.objects.all()}
    except Exception:          # 表未迁移/插件停用时回退静态配置
        switches = {}
    result = []
    for item in getattr(settings, 'OA_PLUGINS', []):
        key = item['app'].rsplit('.', 1)[-1]
        enabled = switches.get(key, item.get('enabled', True))   # DB 优先
        if not enabled:
            continue
        meta = PLUGIN_REGISTRY.get(key)
        if meta:
            result.append((key, meta))
    return result
```

> 注意：静态停用（OA_PLUGINS enabled=False）时**不建开关记录**，DB 无记录仍按静态配置；toggle 只影响 DB 有记录的插件。

## 六、页面

- home.html 增一张"插件开关"卡片（链接 `/plugins/workspace/`），位于"已启用插件"卡片旁
- workspace 插件模板：`workspace/switch_list.html` —— 表格：插件名 / 版本 / 菜单数 / 状态 / **开关**（v1.5.7 起为 Bootstrap `form-check form-switch`，勾选即提交；受保护插件为禁用开关 +「系统必需」）

## 七、验收标准

1. 停用 notice → 刷新：侧栏"公告"消失、`/plugins/notice/` 404、系统其余功能正常
2. 重新启用 → 菜单与路由恢复
3. auth / workspace 开关按钮不可用（禁停）
4. 每次开关操作在留痕链出现 `workspace:plugin_toggled`，链完整性校验通过
5. 无 `workspace_manage` 权限的用户访问开关页被拒（redirect 工作台）

## 八、测试计划

- 单元测试：get_enabled_plugins DB 优先/回退逻辑、toggle 禁停清单、开关状态持久化
- 冒烟：admin 登录 → 停用 notice → 菜单/路由收敛 → 重启服务状态保持 → 留痕链通过

## 九、改动文件清单（✅ 已实现）

| 文件 | 动作 |
|---|---|
| `plugins/workspace/`（apps/models/views/urls/templates/tests/migrations） | 新增（4 项单测） |
| `plugin_host/registry.py` | 改 get_enabled_plugins（DB 优先） |
| `plugin_host/signals.py` | 增 plugin_toggled |
| `plugin_host/middleware.py` | 新增 PluginRouteGuardMiddleware（停用即 404） |
| `plugins/blockchain/apps.py` | 增订阅 plugin_toggled |
| `themes/risograph/templates/home.html` | 增入口卡片 |
| `plugin_host/settings.py` | MIDDLEWARE + OA_PLUGINS 增 workspace 条目 |

## 十、v1.5.7 增补：可停用范围与开关式 UI

### 10.1 禁停清单收敛

- PROTECTED = {'workspace'}：只保护开关入口自身，避免「关掉开关页」导致无法再从 UI 恢复。
- uth / user / structure / language 均可运行时停用；停用 uth 后登录/登出入口 404，已登录会话继续可用。
- 风险提示 CRITICAL_WARNINGS：开关页在 uth / user / structure 行下展示停用后果与恢复命令。

### 10.2 开关 UI

- 每行渲染 Bootstrap orm-check form-switch 复选框（ole="switch"），勾选变化由页面脚本提交表单（不新增内联 onclick）；
oscript 下保留「应用」按钮。
- 受保护插件渲染为已勾选且禁用的开关 +「系统必需」。
- 表单 POST 语义不变：nabled=1 启用、缺省即停用；plugin_toggled 与上链逻辑不变。

### 10.3 兜底命令

`ash
python manage.py plugin_switch list          # 查看全部插件与生效状态
python manage.py plugin_switch off notice
python manage.py plugin_switch on auth       # 停用 auth 后用它恢复登录入口
`

命令不依赖 HTTP、不受禁停清单限制；写 PluginSwitch 并发 plugin_toggled（operator=None）。

### 10.4 工作台入口收敛

停用的插件不再出现在工作台：公告简报卡（notice）、待我审批卡（approval）、考勤待处理卡与「去打卡」（attendance）、插件运维卡（workspace）、流程快捷发起（approval / attendance）均按 plugins_enabled 收敛。
