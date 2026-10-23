# 迭代路线与差距清单（v1.4 → v2.0）

> 依据：`tech-stack-and-architecture.md` / `constraints-and-acceptance.md` / `development-guide.md` 的**全栈插件化**目标
> 负责人校正（2026-10-22）：**不降级**、**补充实现**、**列入修复项**；工作约定只需「文档先行、每改必推 GitHub、每版打 tag」
> 状态：draft-09（2026-10-23）—— **v1.4–v1.5.6 已完成**（144 项测试全绿）；当前推进 v1.6

## 一、总原则

1. **万物皆可插件（同 DSH）**：容器唯一固定；业务、主题、图表、认证、模板引擎、数据库都是可替换的插件 / Provider。
2. **不通过降级文档来匹配现状**：文档承诺的能力，要么实现，要么由负责人明确移出范围；不允许"写不出来就改口径"。
3. **一个迭代一个主题**：先写插件开发文档 → 确认 → 开发 → 单测 + HTTP 冒烟 → 全文档同步 → tag + push。
4. **每版做可插拔自检**：停掉本版涉及的插件 / Provider，系统照常跑，入口收敛。

## 二、差距矩阵（文档承诺 vs 当前代码）

| 能力 | 文档承诺 | 当前实现 | 差距 | 计划 |
|---|---|---|---|---|
| 数据库后端 | MySQL / sqlite / postgres 一行切换 | MySQL / sqlite 通过环境变量切换 | postgres 未验证 | 已具备；v1.10 补验证 |
| 主题 UI | 新建 `themes/<name>` + 改 `OA_THEME` 即换 | Corporate Clean 默认 / Risograph 备选；`OA_THEME` 生效 | 已补齐主题清单、切换、第二主题 | ✅ v1.5 完成 |
| 图表引擎 | 统一 `ChartRenderer`，ECharts 默认 | 无 | 无接口、无 ECharts、无统计接口 | **v1.6** |
| 认证后端 | `AUTHENTICATION_BACKENDS` 可插拔 | 仅 Django 默认 ModelBackend | 无 Provider、无示例后端 | **v1.7** |
| 模板引擎 | Django / Jinja2 可切、可共存 | 仅 DjangoTemplates | 无 Provider、无 Jinja2 | **v1.8**（深度待确认） |
| 插件契约 | `models` / `dependencies` / `admin` / 依赖校验 | 仅 name/version/menus/permissions/urls/signals/templates/app | 字段缺失、无依赖校验 | **v1.9** |
| 业务 ECharts 看板 | 考勤月度统计用 ECharts | 普通表格 | 无图表、无 `/plugins/attendance/stats/` | **v1.6** |
| 插件注册方式 | `OA_PLUGINS` 一行即插即用 | 还需 `INSTALLED_APPS` + `ready()` 注册 | 文档与实现不一致 | **v1.9** 一致性校验 + 文档修正 |
| 会签详情权限 | 会签人可审批 | 非 applicant/approver 且无 `approval_view` 会被重定向 | 权限边界 | **v1.10** 修复 |
| 插件权限准入 | 有权限才能使用插件 | v1.5.3 仅菜单过滤；blockchain / structure / approval 视图未守卫 | 菜单与 URL 口径不一致 | ✅ v1.5.4 统一 `require_perm` + 全员基线 |
| 审批表单 | 按类型动态表单 + 抄送 | v1.5.4 仅三类固定表单 | 类型少、字段固定、无抄送 | ✅ v1.5.5 六类动态表单 + 上下级抄送 |
| 工作台 | 待办优先 + 管理员/员工视图分流 | 静态介绍卡片 | 无待办、无角色分流 | ✅ v1.5.5 四模块排序 + 视图分流 |
| 区块链并发 | 哈希链防篡改 | `append()` 无锁 / 无事务 | 多 worker 可能分叉 | **v1.10** 修复 |
| 运行时开关 | 即时生效 | 静态 disabled 的插件运行中启用需重启 | 路由静态 include | **v1.10** 修复或明确边界 |
| 代码规约 | 禁内联 onclick、raw POST、无事务多步写 | 多处存在 | 质量债务 | **v1.10** 分批清理 |
| 文档一致性 | 文档与代码一致 | 多处 stale（见第五节） | 文档债务 | 随版本 + v1.10 总清 |

## 三、版本路线（建议）

| 版本 | 主题 | 核心交付 | 验收 |
|---|---|---|---|
| **v1.4** | language 中英切换 | `plugins/language` + Cookie 中间件 + 翻译 catalog + 顶栏开关 | ✅ 已完成：13 项单测 + 双语 13 页冒烟 + 全量 51 项通过 |
| **v1.5** | 主题插件化 + Corporate Clean 默认 | ThemeMeta 发现 + `OA_THEME` 生效 + corporate-clean 默认 + risograph 备选 + 登录占位入口 + 首屏 loader（`docs/plugin-dev-theme.md`） | ✅ 已完成：63 项测试 + 双主题冒烟 |
| **v1.5.1** | 全站文案 + 留痕详情 | 插件展示名 / 表头 / 状态 / 空态 / confirm 全量本地化；留痕列表点击查看单条记录 | ✅ 已完成：66 项测试 + Docker 验证 |
| **v1.5.2** | 留痕插件/动作名 | 插件列用 PluginMeta.title，动作列用 action_label，随语言切换 | ✅ 已完成：67 项测试 + Docker 验证 |
| **v1.5.3** | 个人中心 + 权限范围 | 个人中心（资料 / 权限 / 改密）、用户编辑可授予权限过滤、登录回填、公告可见 | ✅ 已完成：76 项测试 + Docker 验证 |
| **v1.5.4** | 权限等级 + 插件准入 | `plugins/user/perms.py` 等级注册表、全员基线权限、角色权限模板（`ROLE_PERMISSIONS` + `grant_role_perms`）、统一 `require_perm`、管理岗签到详情（`attendance_report_view`） | ✅ 已完成：102 项测试 + Docker 验证 |
| **v1.5.5** | 审批动态表单 + 考勤筛选 + 工作台 | 六类审批动态表单、直属上级与抄送、签到状态/类型/时间范围筛选与补卡、工作台待办优先与管理员/员工视图、侧栏高亮、密码权限收紧（`docs/plugin-dev-v155.md`） | ✅ 已完成：138 项测试 + Docker 验证 |
| **v1.5.6** | 组织关系树（责任划分） | 架构总览新增用户关系树：真实账号按 `User.leader` 归并、多级汇报链、直接下属/含下级合计、汇报环与停用显式标记、责任人清单；修复总览「用户模板」分组空白（`docs/plugin-dev-v156.md`） | ✅ 已完成：144 项测试 + 本地 HTTP 三视角冒烟（Docker 待验证） |
| **v1.6** | 图表插件化 + ECharts | `ChartRenderer` 接口；ECharts Provider；考勤 `/stats/` JSON + 月度看板 | 图表数据与打卡记录一致；停用图表插件页面降级不报错 |
| **v1.7** | 认证后端插件化 | `AUTHENTICATION_BACKENDS` Provider；一个无外部依赖的示例后端（如用户名/邮箱） | 切换后端可登录；默认后端仍可用 |
| **v1.8** | 模板引擎插件化 | Django / Jinja2 Provider；先做多引擎共存或单插件切换 | 待确认深度（见第六节） |
| **v1.9** | 插件契约补全 | `models` / `dependencies` / `admin`；依赖顺序与环校验；启用一致性校验 | 缺失依赖启动即报错；停用被依赖插件被拦截 |
| **v1.10** | 修复包 + 文档债务 | 会签详情权限、区块链锁、开关边界、规约清理、全文档同步 | 新增测试全绿；文档与代码无已知冲突 |
| **v2.0** | 最终文档 | 需求规格说明书、测试报告、部署文档、演示脚本（按参考附件） | 负责人验收 |

> 顺序可调整：若希望先补基础设施、把 language 后置，v1.5–v1.8 可整体前移；language 文档已就绪，随时可插入。

## 四、修复项（v1.10 候选，也可提前）

1. **会签详情权限**：`approval_detail` 把「会签人且未签」纳入可访问判定，或要求会签人具备 `approval_view`；补单测。
2. **区块链并发**：`transaction.atomic` + 对最后一条做 `select_for_update`；SQLite 下用进程内锁兜底；补并发/顺序测试。
3. **workspace 静态 disabled 显示**：`switch_list` 回退静态配置而不是默认 `True`；补单测。
4. **静态路由边界**：要么启动时把 DB 启用的插件也纳入路由，要么明确"静态 disabled 的启用需重启"并写进文档。
5. **代码规约债务**：内联 `onclick` → `data-` + 事件绑定；raw `request.POST` → Form；多步写补 `transaction.atomic`；分批做，不夹带功能。
6. **测试盲区**：auth 登录/登出、注册表校验、依赖校验、路由守卫补测试。

## 五、文档债务（需在对应版本同步）

| 文档 | 已知问题 |
|---|---|
| `database-design.md` | v1.4 已修正：language 无表、哈希公式、approval 字段/类型、signer 表、`is_active`/`permission_frozen`；表数口径 v1.10 统一 |
| `plugin-dev-user.md` | v1.4 已加草案警告；v1.10 按实际字段/信号完整重写 §四/§五 |
| `plugin-dev-structure.md` | v1.4 已修正：31 用户；12 一级 + 8 二级 = 20 部门 |
| `README.md` | v1.4 已补 workspace/structure/language 与 roadmap；考勤 ECharts 待 v1.6 |
| `project-overview.md` | v1.4 已补 language；插件示例与"一行注册"v1.10 重写 |
| `constraints-and-acceptance.md` | v1.4 已补进度；"10 张表"口径 v1.10 统一 |
| `development-guide.md` | v1.4 已修正外壳路径 / tag 历史 / 信号数，并补 language 章节；ECharts 与代码规约债务 v1.6–v1.10 |
| `tech-stack-and-architecture.md` | Python 版本与 `PluginMeta.models` 口径 v1.9 统一；基础设施可插拔按 v1.5–v1.8 补齐 |

## 六、待确认的设计深度

1. **模板引擎**：目标是"全站可切 Jinja2"，还是"多引擎共存 + 单插件示例"？全站切换要重写全部模板，成本高。
2. **图表资源**：ECharts 用 CDN（实现快、离线不可用），还是把 `echarts.min.js` 收进静态资源（离线可用、仓库变大）？
3. **主题切换**：改 `OA_THEME` 后重启生效即可，还是要求运行时切换（DB/会话级）？
4. **认证示例后端**：用"用户名或邮箱登录"这种无外部依赖的实现证明可插拔，还是直接做 LDAP/OAuth（要新依赖，需批准）？
5. **v1.4 language**：draft-02 的 5 项是否按推荐（禁停 / 默认中文 / 会话 Cookie / 第六节范围 / `.mo` 不入库）执行？

## 七、每版 DoD

- [ ] 插件开发文档先行，负责人确认
- [ ] 代码 + 独立 migrations（如有表）
- [ ] 新增单测通过；既有测试不回归
- [ ] HTTP 冒烟通过（含 Docker 场景）
- [ ] **Docker 部署成功，提供可访问地址供负责人测试**
- [ ] 可插拔自检通过
- [ ] 全文档同步（本版 + 文档债务中相关项）
- [ ] 打 tag、push GitHub
