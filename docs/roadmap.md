# 迭代路线与差距清单（v1.4 → v2.0）

> 依据：`tech-stack-and-architecture.md` / `constraints-and-acceptance.md` / `development-guide.md` 的**全栈插件化**目标
> 负责人校正（2026-10-22）：**不降级**、**补充实现**、**列入修复项**；工作约定只需「文档先行、每改必推 GitHub、每版打 tag」
> 状态：draft-65（2026-11-11）—— **v1.4–v1.6.20 已交付**（tag **v1.6.20**），**v1.7.0 企业 SSO + 消息提醒**（259 项测试），**v1.7.1 安全与并发修复包**（323 项测试），**v1.7.2 公告极简化 + 考勤规则**（352 项测试），**v1.7.3 共享缓存**（357 项测试），**v1.7.4 登录守卫中间件化**（368 项测试），**v1.7.5 错误页 + 日志与异常分类**（380 项测试），**v1.7.6 列表分页统一 + 公告增量已读 + 留痕翻页**（387 项测试），**v1.7.7 限流计数原子化（P2）+ 认证后端插件化**（403 项测试），**v1.7.8 审计字段统一**（413 项测试），**v1.7.9 越权反馈语义统一（选 403）**（420 项测试），**v1.7.10 对象级越权统一**（427 项测试），**v1.7.11 匿名 JSON 401 + 残留 302 收口**（434 项测试），**v1.7.12 前端接过 401/403**（439 项测试），**v1.7.13 插件开关多 worker 立即可见已交付**（440 项测试）；下一版：按第七节排期

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
| 图表引擎 | 统一 `ChartRenderer`，ECharts 默认 | `plugin_host/charts.py` + `charts/echarts` Provider；`OA_CHARTS` 选择 / 停用降级；v1.6.1 起为 Provider 插件，可运行时启停 | 已补齐清单发现、契约、运行时选择与开关 | ✅ v1.6 / v1.6.1 完成 |
| 认证后端 | `AUTHENTICATION_BACKENDS` 可插拔 | ✅ v1.7.7：`OA_AUTH_BACKENDS` dotted-path 有序链 + `ModelBackend` 垫底 + 契约校验纯函数 + 示例 Provider（用户名/邮箱，含 is_active 检查） | 无 | ✅ v1.7.7 完成 |
| 登录限流计数 | 计数跨 worker 精确 | v1.7.3 起走共享缓存 `get+set`，6 路并发实测计数只有 2/4/4 | 已换独立计数表 `LoginFailureCounter` + `select_for_update`（只锁已存在行）+ 计数封顶 5 | ✅ v1.7.7 完成（容器 5 轮并发均为 5） |
| 审计字段 | 业务表统一带操作人 | v1.7.7 及以前只有 9 个 created_at / 8 个 updated_at，操作人靠 4 处手写 | 已统一为 `AuditModel`（13/14 模型；structure 明确排除），pre_save 自动填；历史行诚实为 NULL | ✅ v1.7.8 完成 |
| 越权反馈 | 已登录无权限的反馈统一 | v1.7.8 及以前 42 条 URL 统一 302 回工作台 | 已统一为 403（HTML 品牌页 / JSON `{code,message}`），未登录仍 302 | ✅ v1.7.9 完成 |
| 运行日志 / 错误页 | 生产可排障、错误页带品牌 | 无 `LOGGING`、无 `templates/400|403|404|500.html`；500 只有默认 traceback 片段 | 已补 `LOGGING`（console，容器不落盘）+ `RequestIdMiddleware`（`X-Request-Id` + 日志 filter）+ 四个错误页 + `ExceptionGuardMiddleware`（业务 400 / 越权 403 / 其它 500） | ✅ v1.7.5 完成 |
| 登录守卫 | 菜单与 URL 同源 `require_perm`；匿名可达面可控 | v1.7.3 及以前靠逐视图 `@login_required`/`require_perm`，无守卫的视图默认可匿名访问 | 已换 `LoginRequiredMiddleware` 默认拦截 + 6 个 `@login_not_required` 白名单，两条集合护栏钉住匿名可达面 | ✅ v1.7.4 完成 |
| 缓存后端 | 文档未承诺（v1.7.3 补齐） | v1.7.2 及以前是 Django 默认 LocMemCache：每 worker 一份，登录限流 / SSO 防重放多 worker 下失效 | 已换 `DatabaseCache`（`constellatio_cache`，跨进程共享，零新依赖） | ✅ v1.7.3 完成 |
| 模板引擎 | Django / Jinja2 可切、可共存 | 仅 DjangoTemplates | 无 Provider、无 Jinja2 | **v1.8**（深度待确认） |
| 插件契约 | `models` / `dependencies` / `admin` / 依赖校验 | 仅 name/version/menus/permissions/urls/signals/templates/app | 字段缺失、无依赖校验 | **v1.9** |
| 业务 ECharts 看板 | 考勤月度统计用 ECharts | 签到详情月度看板 + `/plugins/attendance/stats/` JSON；停用降级表格 | 已补齐图表、统计接口、降级 | ✅ v1.6 完成 |
| 插件注册方式 | `OA_PLUGINS` 一行即插即用 | 还需 `INSTALLED_APPS` + `ready()` 注册 | 文档与实现不一致 | **v1.9** 一致性校验 + 文档修正 |
| 会签详情权限 | 会签人可审批 | v1.7.1 升级为对象级鉴权：申请人 / 审批人 / 会签人 / 抄送人 / 超管；`approval_view`（L3 全员）不再兜底 | 已收敛 | ✅ v1.7.1 完成 |
| 插件权限准入 | 有权限才能使用插件 | v1.5.3 仅菜单过滤；blockchain / structure / approval 视图未守卫 | 菜单与 URL 口径不一致 | ✅ v1.5.4 统一 `require_perm` + 全员基线 |
| 审批表单 | 按类型动态表单 + 抄送 | v1.5.4 仅三类固定表单 | 类型少、字段固定、无抄送 | ✅ v1.5.5 六类动态表单 + 上下级抄送 |
| 工作台 | 待办优先 + 管理员/员工视图分流 | v1.5.5 四模块排序 / 视图分流；v1.6.2 指标卡 + 迷你图 + 趋势大盘 + 插件/组织图表 + 范围筛选 | 已完成图表化 | ✅ v1.5.5 / v1.6.2 完成 |
| 区块链并发 | 哈希链防篡改 | v1.7.1：`append()` 事务 + 链尾 `select_for_update()` + 唯一键重试一次 | 单实例已可靠；多实例分片链路仍待设计 | ✅ v1.7.1 完成（并发用例见 `plugin-dev-v171.md`） |
| 运行时开关 | 即时生效 | v1.7.1：开关仅接受 POST、DB 开关 30s 缓存 + 写失效；静态 `enabled=False` 的插件运行中启用仍需重启 | 路由静态 include | 部分 ✅ v1.7.1；边界 v1.10 明确 |
| 代码规约 | 禁内联 onclick、raw POST、无事务多步写 | v1.7.1：多步写已补 `transaction.atomic`（审批/重新申请/打卡/留痕）；内联 onclick 与 raw POST 仍有多处 | 质量债务（剩余部分） | **v1.10** 分批清理 |
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
| **v1.5.6** | 组织关系树（责任划分） | 架构总览新增用户关系树：真实账号按 `User.leader` 归并、多级汇报链、直接下属/含下级合计、汇报环与停用显式标记、责任人清单；修复总览「用户模板」分组空白（`docs/plugin-dev-v156.md`） | ✅ 已完成：144 项测试 + Docker 重建与三视角冒烟 |
| **v1.5.7** | 插件主权（语言插件化 + 可停用 + 开关 UI） | language 改名「语言」并移出禁停清单、默认语言中间件迁入容器、持久 Cookie 沿用最后语言；`auth / user / structure` 可停用 + 风险提示 + `manage.py plugin_switch` 兜底；停用/启用按钮改为开关；工作台与外壳入口随插件启停收敛（`docs/plugin-dev-v157.md`） | ✅ 已完成：153 项测试 + Docker 重建与冒烟 |
| **v1.5.8** | 功能区主题切换（运行时换肤） | 侧栏「功能」区新增主题按钮组；`oa_theme` Cookie + `ThemeMiddleware` + `ThemeLoader` 按请求换模板；两套主题静态资源同收；非法值回退 `OA_THEME`（`docs/plugin-dev-v158.md`） | ✅ 已完成：158 项测试 + Docker 双主题冒烟 |
| **v1.5.9** | 组织架构合并（当前架构 + 模板详情） | 「组织架构」与「应用结构」合并为单一菜单；组织架构页只展示当前架构（真实部门树 / 角色 / 关系树 / 责任人清单）；模板架构移到 `/plugins/structure/template/`，从【查看模板】进入，应用模板留在模板页（`docs/plugin-dev-v159.md`） | ✅ 已完成：163 项测试 + Docker 双视角冒烟 |
| **v1.5.10** | 角色卡片弹窗与滚动 | 「当前角色」改为可点击卡片，弹窗展示角色成员（姓名/账号/部门/停用）；角色列表限高可滚动、随视口自适应（`docs/plugin-dev-v1510.md`） | ✅ 已完成：164 项测试 + Docker 冒烟 |
| **v1.5.11** | 角色列表布局修正 | 左右卡片等高等宽；高度上限收敛到卡片、内层 flex 撑满滚动；消除右侧/底部无效空白，角色多时仅卡片内滚动（`docs/plugin-dev-v1511.md`） | ✅ 已完成：164 项测试 + Docker 重建 |
| **v1.5.12** | 角色成员弹窗修复 + 用户资料 | 修复角色卡片点击无弹窗（脚本提前于 bootstrap 加载）；弹窗成员可点击进入 `/plugins/structure/user/<id>/` 只读资料（部门/角色/上级/状态/邮箱等），责任人清单同样可点（`docs/plugin-dev-v1512.md`） | ✅ 已完成：169 项测试 + Docker 重建 |
| **v1.5.13** | 角色弹窗居中浮出 | 弹窗改用 `modal-dialog-centered` 垂直/水平居中；scoped CSS 缩放淡入（180ms，尊重 reduced-motion），保留内部滚动（`docs/plugin-dev-v1513.md`） | ✅ 已完成：169 项测试 + Docker 重建 |
| **v1.5.14** | 报销金额 + 用章附件 | 报销新增金额*（落 `Approval.amount`）；用章拆为「用章文件*」与「用途」，附件落盘并走权限下载 `/plugins/approval/<id>/attachment/`；compose 加 media 卷（`docs/plugin-dev-v1514.md`） | ✅ 已完成：172 项测试 + Docker 重建 |
| **v1.5.15** | 审批路由 + 用章盖章占位 | L3 隐藏待我审批（菜单/视图/工作台）；调休改为起止时间段；审批按类型路由到管辖部门（HR/财务/行政）；用章通过后写入电子盖章占位与流转记录（`docs/plugin-dev-v1515.md`） | ✅ 已完成：177 项测试 + Docker 重建 |
| **v1.5.16** | 驳回申请重新申请 / 隐藏 | 已驳回可一键重新申请（复制并重新待审批）；删除申请记录=对申请人隐藏（`applicant_hidden`），数据与留痕保留；迁移 0006（`docs/plugin-dev-v1516.md`） | ✅ 已完成：180 项测试 + Docker 重建 |
| **v1.5.17** | 重申请表单化 + 审批终态 | 「重新申请」进入预填可编辑表单，确认后新单替换驳回记录（`replaced_by` + 隐藏）；审批操作二次确认且终态不可修改；详情隐藏空内容项；抄送我的对 L3 隐藏；补站内信计划（`docs/plugin-dev-v1517.md`） | ✅ 已完成：184 项测试 + Docker 重建 |
| **v1.5.18** | 审批人限定业务负责人 + 抄送直系领导 | 审批人候选限定为管辖部门负责人（无留空、必选）；抄送改为申请人直系领导（领导=申请人/审批人时跳过）；无迁移（`docs/plugin-dev-v1518.md`） | ✅ 已完成：184 项测试 + Docker 重建 |
| **v1.6** | 图表插件化 + ECharts | `ChartRenderer` 接口 + `charts/echarts` Provider（本地 ECharts 5.5.1）；考勤 `/plugins/attendance/stats/` JSON + 签到详情月度看板；`OA_CHARTS` 停用降级表格（`docs/plugin-dev-v16.md`） | ✅ 已实现：204 项测试 + Docker 重建；图表数据与打卡记录同源、停用后 200 降级 |
| **v1.6.1** | 图表运行时开关 + 留痕链统计 | 图表引擎注册为 Provider 插件（`PluginSwitch` 运行时开关，UI / CLI 即时生效并上链）；留痕链 `/plugins/blockchain/stats/` 按日 × 来源插件统计 + 看板 / 表格降级（`docs/plugin-dev-v161.md`） | ✅ 已实现：220 项测试 + Docker 重建；开关关停后两处看板均降级表格、统计与留痕记录一致 |
| **v1.6.2** | 工作台图表化大盘 | 4 张指标卡（数字 + 迷你图）、流程趋势多曲线、插件分布饼图、组织人员柱状图；今日 / 本周 / 本月联动筛选；管理员 / 员工视图分流；点击跳转 / 告警色 / 响应式（`docs/plugin-dev-v162.md`） | ✅ 已实现：231 项测试 + Docker 重建；管理员 / 员工区块差异、范围联动、告警、降级与两套主题均验证 |
| **v1.6.3** | 工作台 Banner 白字 + 侧栏吸顶 | Corporate Clean hero 标题 / 欢迎语改白字（Risograph 不变）；两套主题侧栏 `position: sticky`（桌面端，菜单超长栏内滚动）；其余布局与交互不变（`docs/plugin-dev-v163.md`） | ✅ 已实现：234 项测试 + Docker 重建；Corporate 白字、Risograph 原配色、吸顶与移动端不变均验证 |
| **v1.6.4** | 顶部导航栏吸顶 | 两套主题 `.r-nav` 改为 `position: sticky; top: 0; z-index: 1030`（白底 / 纸色底 + 原边框），滚动时导航保持在视口顶部；侧栏 sticky 与其余布局不变（`docs/plugin-dev-v164.md`） | ✅ 已实现并部署；按要求未跑自动化测试，滚动吸顶由负责人验证 |
| **v1.6.5** | 指标卡按钮底部居中与基线对齐 | 四张指标卡改 `d-flex flex-column`，按钮 footer `mt-auto` 置底 + 水平居中，四卡等高 → 按钮同一基线；告警徽标移出 footer（`docs/plugin-dev-v165.md`） | ✅ 已实现并部署；按要求未跑自动化测试，按钮对齐由负责人验证 |
| **v1.6.6** | 插件分布卡片紧凑化 | 去 `h-100` 高度自适应、图表 300→240px、图例 / 分页 / 文案间距收紧（饼图 option 紧凑化）（`docs/plugin-dev-v166.md`） | ✅ 已实现并部署；按要求未跑自动化测试，紧凑度由负责人验证 |
| **v1.6.7** | 指标卡按钮统一与去箭头 | 四按钮统一 `r-btn`（审批中心去 plain）；移除文本尾部 `→`；布局 / 数据不变（`docs/plugin-dev-v167.md`） | ✅ 已实现并部署；按要求未跑自动化测试 |
| **v1.6.8** | 部门明细表格拆分 | 「组织人员」卡只留柱状图；部门表格移出为独立「部门明细」卡片，置于两图并排行下方；数据 / 样式不变（`docs/plugin-dev-v168.md`） | ✅ 已实现并部署；按要求未跑自动化测试 |
| **v1.6.9** | 图表双卡等宽等高 | 插件分布卡恢复 `h-100`、图表 240→300px；两卡 `col-lg-6` 等宽、行内等高，图表随容器自适应（`docs/plugin-dev-v169.md`） | ✅ 已实现并部署；按要求未跑自动化测试 |
| **v1.6.10** | 公告简报卡片化 + 列表/详情合并 | 工作台公告改独立卡片流；公告中心列表 + 内联详情同页（`?notice=`），标题/辅助信息/正文分层；旧详情链接 302 兼容；发布后直达详情（`docs/plugin-dev-v1610.md`） | ✅ 已实现：237 项测试 + Docker 重建 |
| **v1.6.11** | 部门管理页排版优化 | 左右分栏顶部对齐；表格宽松内边距 + 垂直居中；操作按钮等距并区分修改 / 停用 / 删除（新增 `r-btn--danger`）；表单控件等宽左对齐（`docs/plugin-dev-v1611.md`） | ✅ 已实现：237 项测试 + Docker 重建 |
| **v1.6.12** | 角色 / 审批 / 待办三页统一排版 | 三页统一 `r-table--roomy align-middle`；表头深色；权限码流式换行；状态标签四态配色；审批操作列结构修复；待办角标与去审批按钮对齐（`docs/plugin-dev-v1612.md`） | ✅ 已实现：237 项测试 + Docker 重建 |
| **v1.6.13** | 用户管理 + 角色权限码排版 | 用户操作区风险配色（编辑链接 / 冻结蓝 / 禁用红）、超管弱化、标签流式换行；角色权限码固定列宽自动折行、顶部对齐；两页表格与全站统一（`docs/plugin-dev-v1613.md`） | ✅ 已实现：237 项测试 + Docker 重建 |
| **v1.6.14** | 用户管理操作项按钮化 | 编辑改白底蓝字按钮，冻结 / 启停蓝色主按钮，禁用红色危险按钮；新增 `.r-btn--action` 统一操作按钮宽度；超管行仅保留灰色提示（`docs/plugin-dev-v1614.md`） | 用户模块 25 项通过并部署；全量 235/237（2 项考勤跨日时钟边界既有问题） |
| **v1.6.15** | 公告中心双卡片改版 | 移除列表表格，左信息卡（含「已读」按钮 + 已读人员弹窗 + 切换公告）右详情卡；元信息弱化、正文独立区块、底部返回列表（`docs/plugin-dev-v1615.md`） | notice 6 项通过并部署；全量 235/237（既有跨日边界） |
| **v1.6.16** | 考勤 / 签到详情页面优化 | 考勤页标题改「考勤」+ 新增个人月度考勤图表卡（个人状态堆叠柱 / 降级表格）；签到详情筛选区压缩为单行自适应布局（`docs/plugin-dev-v1616.md`） | 考勤 23/25（2 项既有跨日边界）并部署；全量 235/237 |
| **v1.6.17** | 考勤卡片收紧 / 按钮同行 / 改名 | 两卡去 `h-100` 收紧高度；签到 / 签退与类型下拉合并同行、按钮统一尺寸；插件名「考勤打卡」→「考勤」（`docs/plugin-dev-v1617.md`） | rbac / attendance / user 63/65（2 项既有跨日边界）并部署 |
| **v1.6.18** | 今日状态卡片压缩等高 | 状态徽标与签到时间同行、标题/控件间距收紧；两卡 `h-100` 保持与本月统计等高（`docs/plugin-dev-v1618.md`） | 纯模板调整并部署 |
| **v1.6.19** | 部门操作按钮配色调整 | 修改改白底蓝字按钮、停用改蓝色按钮，物理删除保持红色；三者统一 `r-btn--action`（`docs/plugin-dev-v1619.md`） | 纯模板调整并部署 |
| **v1.6.20** | 部门状态徽标绿色与防折行 | 状态列 `text-nowrap` 防止「启用」折行；启用徽标改绿色（`r-badge--green`）（`docs/plugin-dev-v1620.md`） | 纯模板调整并部署 |
| **v1.7** | 认证后端插件化 | `AUTHENTICATION_BACKENDS` Provider；一个无外部依赖的示例后端（如用户名/邮箱） | 切换后端可登录；默认后端仍可用（延期，见 v1.7.1） |
| **v1.7.0** | 企业 SSO + 站内信提醒 | `plugins/sso`（HMAC Ticket 网关、自动建号、防重放、登录页入口、`sso_ticket` 命令）；`plugins/notify`（消息中心 / 顶栏未读 / 审批待办与结果 / 公告提醒 / 工作台我的消息 / 停用降级）（`docs/plugin-dev-sso.md`、`docs/plugin-dev-notify.md`） | ✅ 已实现：259 项测试 + Docker 重建 |
| **v1.7.1** | 安全与并发修复包（原 v1.10 候选提前） | P0-B 并发（审批行锁 / 留痕链锁 / 打卡丢更新）、P0-C 授权（对象级鉴权 / 审批人收口 / 编辑页不得改状态 / 开关仅 POST）、P1 十四项（传输安全、登录限流、注册表系统检查、开关缓存、菜单 N+1、信号隔离、分页、校验快照、工程化门禁）（`docs/plugin-dev-v171.md`） | ✅ 已交付：323 项测试 + ruff/CI + Docker 重建与 9 页冒烟 |
| **v1.7.2** | 公告极简化 + 考勤规则 | notice：单列公告流（标题 + 正文同屏）、进入即已读、已读统计下沉为管理岗页、旧详情链接锚点兼容；attendance：`AttendanceRule` 单例（上下班 / 宽限 / 工作日 / 补卡回溯）、`/plugins/attendance/rules/` 设置页、`attendance_rule_manage` 权限、看板口径展示（`docs/plugin-dev-v172.md`） | ✅ 已交付：352 项测试 + Docker 重建与页面冒烟 |
| **v1.7.3** | 共享缓存（跨 worker） | `CACHES` 换 `DatabaseCache`（`constellatio_cache`，`TIMEOUT=900`、`MAX_ENTRIES=10000`）；`entrypoint.sh` 在 migrate 后 `createcachetable`；README 本地步骤；`TEST_RUNNER` 为测试库建表（`docs/plugin-dev-v173.md`） | ✅ 已交付：357 项测试 + 3 worker 容器验收 + 生产 MySQL 唯一键实测 |
| **v1.7.4** | 登录守卫中间件化（默认拦截 + 显式白名单） | `MIDDLEWARE` 插入 `LoginRequiredMiddleware`（AuthenticationMiddleware 之后）；auth 三视图 + sso 两视图 + language 切换共 6 个 `@login_not_required`；两条集合护栏钉住匿名可达面；admin 行为断言（`docs/plugin-dev-v174.md`） | ✅ 已交付：368 项测试 + 3 worker 容器验收（含收尾的登录回跳） |
| **v1.7.5** | 错误页 + 日志与异常分类 | 四个错误页（400/403/404/500，404/403/400 extends 外壳、500 独立渲染）+ `DIRS`/filesystem loader；`LOGGING`（console，容器不落盘；`DJANGO_LOG_TO_FILE` 默认 0）+ `RequestIdMiddleware`（`X-Request-Id` + filter）；`BusinessError`(400) / `ObjectPermissionDenied`(403) / `ExceptionGuardMiddleware`；两个 JSON 接口错误体统一 `{code,message}`（`docs/plugin-dev-v175.md`） | ✅ 已交付：380 项测试 + 容器 404/500/JSON 冒烟 |
| **v1.7.6** | 列表分页统一 + 公告增量已读 + 留痕翻页 | 新增 `plugin_host/pagination.py`（唯一分页入口）+ `templates/includes/pagination.html`（两套主题共用，`{% querystring %}` 保住筛选参数）；approval/attendance 去掉内联 `Paginator`；user 部门/用户、notice 列表接分页；notice 只登记当页未读；留痕 50/页 + 总数 + 看板 60 秒快照（`docs/plugin-dev-v176.md`） | ✅ 已交付：387 项测试 + 容器手工验收（693 条 → 14 页，末页 43 行） |
| **v1.7.7** | 限流计数原子化（P2）+ 认证后端插件化 | **首项 P2**：`plugins/auth` 新增 `LoginFailureCounter`（独立表 + `select_for_update`，只对已存在行加锁避免 gap 锁死锁，计数封顶 5）；随后 `OA_AUTH_BACKENDS` dotted-path 有序链 + `ModelBackend` 垫底 + `validate_auth_backends()` 纯函数契约校验 + 示例 Provider（用户名/邮箱，过 `user_can_authenticate`）（`docs/plugin-dev-v177.md`） | ✅ 已交付：403 项测试 + 容器 MySQL 6 路并发 ×5 轮（计数稳定 5、0 次 500）+ 单 worker 对照 + email 登录冒烟 |
| **v1.7.8** | 审计字段统一（AuditModel） | 抽象 `AuditModel`（created_at/updated_at 均 null=True + created_by/updated_by）+ `current_user` contextvar + `CurrentUserMiddleware`（匿名→None，finally 复位）+ `pre_save` 统一填充；三批迁移（notify/blockchain/workspace → approval/attendance/notice → user），迁移末尾 RunSQL 清除被框架注入的时间默认值；structure 明确排除（`docs/plugin-dev-v178.md`） | ✅ 已交付：410 项测试 + 三批迁移回滚往返 + 容器 HTTP created_by 核验 + 13/14 模型覆盖 |
| **v1.7.9** | 越权反馈语义统一（选 403） | `require_perm` 一处改动：已登录无权限码由 `redirect('index')` 改为 `raise ObjectPermissionDenied`（31 个视图 / 42 条 URL 同时生效）；未登录仍 302 到登录页带 next；JSON 接口复用 `_wants_json`；同时修 `_error_response` 丢弃 `exception.message` 与日志只打 code 的问题（`docs/plugin-dev-v179.md`） | ✅ 已交付：420 项测试 + 403 品牌页/`{code,message}`/`next` 三种口径用例 + 禁止项 8 条全部遵守 |
| **v1.7.10** | 对象级越权语义统一 | 审批详情 GET/POST、附件下载、`approval_hide` 的对象级越权由 302/404 统一为 **403**；`services` 抛的 `PermissionError` 不再被静默吞掉；文案「该审批单不属于你」/「你无权审批该单据」只进 JSON 与日志（`docs/plugin-dev-v1710.md`） | ✅ 已交付：427 项测试 + 附件无字节流出断言 + 容器冒烟 |
| **v1.7.11** | 匿名 JSON 401 + 残留功能级 302 收口 | `LoginRequiredMiddleware` 换成子类 `JsonAwareLoginRequiredMiddleware`：匿名 + 要 JSON → **401 JSON**，HTML 仍 302 带 next；JSON 判据收敛为模块级 `wants_json()`（异常守卫与登录守卫共用一份）；`attendance_check` 手写 `has_perm` 由 302 改为 403（`docs/plugin-dev-v1711.md`） | ✅ 已交付：433 项测试 + 容器实测 401/302/403 三口径分离 |
| **v1.7.12** | 前端接过 401 / 403 | 两处 stats `fetch` 的 `!response.ok` 分支原本只 `throw`，401/403/500 在前端同色；抽 `templates/includes/stats_fetch_fail.js`（`handleStatsFailure`）：401 → 跳登录并带 `next`（页面 URL，非接口地址）、403 → 「无权查看该数据」、其它 → 「数据暂时不可用」；`showEmpty(text)` 支持文案；`null` 作哨兵（`docs/plugin-dev-v1712.md`） | ✅ 已交付：439 项测试 + 渲染后 JS 的 node 桩 DOM 实测（401 的 next / 403 文案 / 500 兜底） |
| **v1.7.13** | 插件开关多 worker 立即可见（删进程内缓存） —— ✅ 已交付：440 项测试 + 3 worker 实测（新代码 6/6 拦截，旧代码 6/6 放行），验收判据为「有缺陷的代码必须过不了」 | `registry.py` 的进程内 TTL 缓存导致多 worker 下停用插件后 ~30 秒才生效；**方案：直接删掉缓存**（信号驱动在多进程下只清本进程，会把缺陷伪装成已修复；版本号驱动需共享存储、成本与直接查表相同）；同时删 `PLUGIN_SWITCH_CACHE_TTL` / `PLUGIN_SWITCH_ERROR_TTL` / `invalidate_plugin_switch_cache` 与 workspace 的失效钩子（`docs/plugin-dev-v1713.md`） | 验收必须**两 worker**：worker A 停用后立刻连打请求，access log 确认落在至少两个不同 pid，且全部呈现停用语义；对照实验（删缓存前的代码）必须能复现旧行为 |
| **v1.8** | 模板引擎插件化 | Django / Jinja2 Provider；先做多引擎共存或单插件切换 | 待确认深度（见第六节） |
| **v1.9** | 插件契约补全 | `models` / `dependencies` / `admin`；依赖顺序与环校验；启用一致性校验 | 缺失依赖启动即报错；停用被依赖插件被拦截 |
| **v1.10** | 剩余修复包 + 文档债务 | P0-A 部署默认值（密钥/口令/DEBUG/HOSTS）、容器非 root 与健康检查、`entrypoint` 注入、`has_perm` 三处口径、模板内联 JS 与 inline style、静态停用边界、全文档同步 | 新增测试全绿；文档与代码无已知冲突 |
| **v1.15** | 信息提醒插件（计划） | `plugins/notify`：站内信 / 公告 / 审批结果与待办通知、消息中心与未读数（`docs/plugin-dev-notify.md`） | ✅ 提前于 v1.7.0 完成：审批/公告产生消息、未读与已读、越权不可见、停用降级 |
| **v2.0** | 最终文档 | 需求规格说明书、测试报告、部署文档、演示脚本（按参考附件） | 负责人验收 |

> **版本号在交付时分配，执行顺序以本表顺序为准**（2026-11-10 起）。
> **排期让位（合并说明，随 v1.7.7 交付闭环）**：v1.7.4 起 **连续三项安全/可用性修复插队**——v1.7.4 登录守卫中间件化（先定「哪些视图匿名」再换认证实现，反过来要改两遍）、v1.7.5 错误页与日志（可观测性前置）、v1.7.6 列表分页与公告写入（A5 是会丢筛选参数的真实缺陷）。「认证后端插件化 + P2 计数原子化」因此顺延到 **v1.7.7**（P2 仍第一项），越权反馈语义统一顺延 **v1.7.8（待定）**。
> 顺序可调整：若希望先补基础设施、把 language 后置，v1.5–v1.8 可整体前移；language 文档已就绪，随时可插入。

## 四、修复项（原 v1.10 候选）

> v1.7.1 已完成第 1、2、6 项，以及第 3、5 项的大部分；剩余项移入 v1.10（见第三节）。

1. ✅ **会签详情权限**（v1.7.1）：不再以 `approval_view` 兜底，改为对象级鉴权（申请人 / 审批人 / 会签人 / 抄送人 / 超管）；已补 10 项越权与分页用例。
2. ✅ **区块链并发**（v1.7.1）：`transaction.atomic` + 链尾 `select_for_update`，唯一键冲突重试一次；SQLite 下为 no-op，已在文档标注。
3. ◐ **workspace 静态 disabled 显示**（v1.7.1 部分）：开关改为 POST + 缓存失效；`switch_list` 的静态回退口径待与 v1.9 的启用一致性校验一起收口。
4. ◻ **静态路由边界**：要么启动时把 DB 启用的插件也纳入路由，要么明确「静态 disabled 的启用需重启」并写进文档（v1.10）。
5. ◐ **代码规约债务**（v1.7.1 部分）：多步写已补 `transaction.atomic`；内联 `onclick` 与 raw `request.POST` 仍待分批清理（v1.10）。
6. ✅ **测试盲区**（v1.7.1）：注册表校验、开关缓存、登录限流、对象级鉴权、链写入、打卡并发均已补测；`plugin_host/tests_registry.py` 用「逐条 has_perm」参考实现验证菜单权限集合等价。
7. ◻ **限流计数原子化（P2，v1.7.5 第一项）**：v1.7.3 交付前自检实测——6 路并发错密码全部计错、最终计数 2/4/4（串行口径应在 5 处封顶并拦第 6 次），根因是 `_record_failure()` 的 get+set 丢更新；`DatabaseCache` 未覆盖 `incr`，继承的 `BaseCache.incr` 同样是 get+set 且 `set` 不传 timeout（窗口被重置为默认 TTL）。方案：auth 插件独立计数表 + `select_for_update` + `F('count')+1`。**注意**：不能在 `constellatio_cache.value` 上做 SQL 自增（存的是 `base64(pickle)`）。
8. ✅ **运行日志缺失（v1.7.5 已修）**：`LOGGING` + `RequestIdMiddleware`（`X-Request-Id`）+ 四个错误页 + `ExceptionGuardMiddleware`。容器只走 console（`DJANGO_LOG_TO_FILE` 默认 0，多 worker 不轮转同一文件）；实测 500 场景日志含 request_id 与完整栈。
9. ✅ **账号密码登录不消费 `next`（v1.7.4 收尾已修）**：装 `LoginRequiredMiddleware` 后 42 条 URL 全部开始带 `next`，把原来的「偶发」放成「默认路径」，且 SSO 通道已能回跳、同一登录页两种结果，故在 v1.7.4 收尾用 `fix(auth)` 修复：`_next_target()` + `_redirect_after_login()`（`url_has_allowed_host_and_scheme` 校验，外站与 `//host` 均拒）+ 两套主题 `login.html` 补隐藏域 + `render` 上下文补 `next`；补 3 条用例（回跳带查询串 / 外站拒 / 协议相对拒），测试 365 → 368。不动 v1.7.4 tag。
10. ◻ **真机浏览器冒烟（上线前必做，v1.7.12 遗留）**：v1.7.12 的 401 跳转只有 node 桩 DOM 验证，上线前需在真实浏览器打开列表页并确认「跳转到登录页 + next 正确 + CSP 未拦截」。
11. ◻ **越权反馈语义统一（302 / 403 / 404 三选一，v1.7.9 待定）**：局部迁移会造出第二种反馈（同一用户被拒，有时回工作台、有时 403），v1.7.4 刚修掉同类不一致，不能重犯。三种语义的泄漏面与适用场景：302 不泄漏对象存在 / 403 泄漏「存在但无权」便于找审批人 / 404 完全不泄漏适合对外接口。决定后一次性迁移 43 处装饰器口径，并把 `BusinessError` 真实抛点（审批重复提交、补卡超窗口等）一起接上。

## 五、文档债务（需在对应版本同步）

| 文档 | 已知问题 |
|---|---|
| `database-design.md` | v1.4 已修正：language 无表、哈希公式、approval 字段/类型、signer 表、`is_active`/`permission_frozen`；表数口径 v1.10 统一 |
| `plugin-dev-user.md` | v1.4 已加草案警告；v1.10 按实际字段/信号完整重写 §四/§五 |
| `plugin-dev-structure.md` | v1.4 已修正：31 用户；12 一级 + 8 二级 = 20 部门 |
| `README.md` | v1.4 已补 workspace/structure/language 与 roadmap；v1.6 已补图表插件与月度看板 |
| `project-overview.md` | v1.4 已补 language；插件示例与"一行注册"v1.10 重写 |
| `constraints-and-acceptance.md` | v1.4 已补进度；"10 张表"口径 v1.10 统一 |
| `development-guide.md` | v1.4 已修正外壳路径 / tag 历史 / 信号数，并补 language 章节；v1.6 已把图表改为 Provider + 本地资源；代码规约债务 v1.10 |
| `tech-stack-and-architecture.md` | Python 版本与 `PluginMeta.models` 口径 v1.9 统一；基础设施可插拔按 v1.5–v1.8 补齐 |

## 六、待确认的设计深度

1. **模板引擎**：目标是"全站可切 Jinja2"，还是"多引擎共存 + 单插件示例"？全站切换要重写全部模板，成本高。
2. **图表资源**：✅ v1.6 决策——`echarts.min.js` 收进 Provider 静态资源（离线可用，仓库 +1 MB），不再依赖 CDN。
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
