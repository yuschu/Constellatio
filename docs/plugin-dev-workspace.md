# 插件开发文档：workspace（工作台可启用/禁用功能）

> 关联插件：plugin_host 容器（registry 运行时开关）
> 版本规划：v1.1 · 文档版本：draft-01 · 2026-10-21
> 状态：**待确认后开发**

## 一、需求

工作台新增"可启用/禁用功能"：在系统内（工作台入口）以开关形式**运行时**启用/停用各插件，无需改 `OA_PLUGINS` 配置、无需重启。操作即时生效、留痕上链。

## 二、设计要点

| 项 | 决策 |
|---|---|
| 形态 | 新插件 `plugins/workspace`（"万物皆可插件"：管理能力本身也是插件） |
| 运行时开关 | 新建表 `workspace_pluginswitch`（app_key, enabled）持久化，**DB 优先覆盖** settings.OA_PLUGINS 静态配置 |
| 生效机制 | `registry.get_enabled_plugins()` 改造：先读 DB 开关，无记录回退静态配置；路由动态 include / 菜单聚合 / 权限收敛均基于它 → 一次请求即生效 |
| 防锁死 | `auth`、`workspace` 自身禁止停用（保证登录与开关入口永在） |
| 权限 | 新权限码 `workspace_manage`（普通管理员即可操作，即时生效） |
| 上链 | 开关操作发 `plugin_toggled` 信号 → blockchain 订阅上链 |
| 页面 | home 工作台新增"插件开关"入口卡片 → `/plugins/workspace/` 开关页（插件列表 + 开关按钮） |

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
| `/plugins/workspace/<app_key>/toggle/` | switch_toggle | POST；校验禁停清单（auth/workspace）；写 DB → 发 `plugin_toggled` → 上链；返回列表页 |

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
- workspace 插件模板：`workspace/switch_list.html` —— 表格：插件名 / 版本 / 菜单数 / 开关按钮（Riso r-btn）

## 七、验收标准

1. 停用 notice → 刷新：侧栏"公告"消失、`/plugins/notice/` 404、系统其余功能正常
2. 重新启用 → 菜单与路由恢复
3. auth / workspace 开关按钮不可用（禁停）
4. 每次开关操作在留痕链出现 `workspace:plugin_toggled`，链完整性校验通过
5. 无 `workspace_manage` 权限的用户访问开关页被拒（redirect 工作台）

## 八、测试计划

- 单元测试：get_enabled_plugins DB 优先/回退逻辑、toggle 禁停清单、开关状态持久化
- 冒烟：admin 登录 → 停用 notice → 菜单/路由收敛 → 重启服务状态保持 → 留痕链通过

## 九、改动文件清单

| 文件 | 动作 |
|---|---|
| `plugins/workspace/`（apps/models/views/urls/templates/migrations） | 新增 |
| `plugin_host/registry.py` | 改 get_enabled_plugins |
| `plugin_host/signals.py` | 增 plugin_toggled |
| `plugins/blockchain/apps.py` | 增订阅 |
| `themes/risograph/templates/home.html` | 增入口卡片 |
| `plugin_host/settings.py` | OA_PLUGINS 增 workspace 条目 |
