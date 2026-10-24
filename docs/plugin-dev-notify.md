# 插件开发：notify（信息提醒：站内信 / 公告 / 审批信息）

> 状态：**✅ 已实现（v1.7.0）** · 文档日期：2026-10-24（原计划 v1.15 提前落地）
> 关联：approval（审批结果/待办）、notice（公告）、user（接收人）、plugin_host（信号 / 菜单 / 工作台）

## 一、目标

为系统提供统一的信息提醒能力，首期覆盖三类消息：

| 类别 | 触发 | 接收人 |
|---|---|---|
| 审批结果 | `approval_finished`（通过 / 驳回） | 申请人 |
| 审批待办 | 审批单进入 pending（含抄送） | 审批人 / 抄送人 |
| 公告发布 | `notice_published` | 全员（或按公告可见范围） |
| 系统消息 | 用户禁用 / 部门删除 / 插件开关等（可选） | 相关人 / 管理员 |

## 二、设计要点

| 项 | 决策（待确认） |
|---|---|
| 形态 | 新插件 `plugins/notify`（可停用；停用后仅失去提醒，不影响业务） |
| 模型 | `Notification(recipient, category, title, body, link, is_read, read_at, created_at)`；索引 `(recipient, is_read)` |
| 产生方式 | 只订阅 `plugin_host.signals`，不反向 import 业务插件；审批待办需在 approval 增加 `approval_submitted` 信号 |
| 入口 | 顶栏铃铛 + 未读数；`/plugins/notify/` 消息中心；工作台「我的消息」卡片（最新 3 条） |
| 权限 | 本人只能看自己的消息；`notify_view` 为全员基线（与考勤/公告一致） |
| 已读 | 单条已读 + 全部已读；访问详情跳转业务页并标记已读 |
| 双语 | 标题 / 正文由触发方传 gettext 后的文本；界面文案进 `.po` |
| 可插拔自检 | 停用 notify → 菜单/铃铛消失、业务照常；不产生遗留报错 |
| 不做的 | IM / 邮件 / 短信实时推送（后续用 Provider 扩展）；不做消息模板管理后台 |

## 三、版本拆解（建议）

1. **v1.15.0 契约 + 模型**：`Notification` 模型、`notify_view` 全员基线、信号占位、插件注册（菜单/URL）。
2. **v1.15.1 审批消息**：approval 增加 `approval_submitted` 信号；订阅 `approval_finished` / `approval_submitted` 写站内信；工作台卡片。
3. **v1.15.2 公告消息**：订阅 `notice_published` 批量写全员消息（大组织需分页/批量插入）。
4. **v1.15.3 消息中心**：列表 / 详情跳转 / 已读 / 未读数徽标；双语文案。
5. **v1.15.4 验收**：单测（产生 / 权限 / 已读 / 停用降级）、Docker 冒烟、文档与快照。

## 四、验收标准（计划）

- 审批通过/驳回后，申请人收到站内信，未读数 +1；
- 审批待办产生后，审批人收到通知（抄送人收到抄送消息）；
- 公告发布后，全员消息中心可见（或按可见范围）；
- 他人消息不可见（越权 302/404）；已读状态持久；
- 停用 notify 插件后菜单与铃铛消失，业务不受影响；
- 中英文切换完整；Docker 重建后可用。

## 五、依赖与风险

- 依赖 v1.5.10+ 权限体系与插件开关（`workspace`）；
- 审批待办信号需要改 approval（本计划先加信号，不改变状态机）；
- 公告全员写入在 31 用户规模无压力；更大规模需批量插入 + 异步任务（暂不引入队列）；
- 与既有「公告插件」边界：公告负责内容，notify 负责提醒，不重复实现公告列表。

## 六、站内信（Inbox）细化方案

站内信是首期最先落地的能力，先于公告/系统消息：

| 项 | 方案 |
|---|---|
| 路由 | `/plugins/notify/` 消息中心（全部 / 未读筛选）；`/plugins/notify/read/<id>/` 已读并跳转业务链接 |
| 模型 | `Notification(recipient, category[approval/notice/system], title, body, link, is_read, read_at, created_at)`；索引 `(recipient, is_read)` |
| 未读数 | 顶栏铃铛 + `unread_count` 上下文处理器（仅登录用户，一次 count 查询） |
| 产生 | 站内方法 `notify.send(recipients, ...)`；业务插件只发信号，由 notify 订阅（零反向依赖） |
| 已读 | 单条已读、全部已读；详情跳转后标记已读（GET 跳转，不做可被预取的自动已读） |
| 边界 | 不做 IM/邮件/短信；不做消息模板后台；停用插件后铃铛与入口消失，业务不受影响 |

### 6.1 版本拆解（站内信优先）

1. **v1.15.0**：`Notification` 模型 + `notify` 插件注册 + 消息中心列表 / 已读 / 未读数 + 全员基线 `notify_view`；
2. **v1.15.1**：审批站内信（approval 增加 `approval_submitted` 信号，订阅 `approval_finished`）→ 申请人结果、审批人待办；
3. **v1.15.2**：公告站内信（订阅 `notice_published`，按可见范围写入）；
4. **v1.15.3**：工作台「我的消息」卡片 + 双语文案 + 停用降级验收。

### 6.2 验收（站内信）

- 审批通过/驳回 → 申请人收到站内信，未读数 +1；
- 审批待办 → 审批人收到站内信；
- 越权访问他人消息 404；已读状态持久；全部已读生效；
- 停用 notify → 铃铛与入口消失、业务照常。

## 七、v1.7.0 实现记录（2026-10-24）

| 项 | 实现 |
|---|---|
| 插件 | `plugins/notify`（Django app，可停用）；菜单「消息中心」`/plugins/notify/`；`notify_view` 全员基线 |
| 模型 | `Notification(recipient, category, title, body, link, is_read, read_at, created_at)` + `(recipient, is_read)` 索引；迁移 `0001_initial` |
| 信号 | 新增 `approval_submitted`（`services.submit` / `start_counter_signature` 发送）；订阅 `approval_submitted` / `approval_finished` / `notice_published`；通知失败不影响业务 |
| 待办消息 | 接收人 = 审批人 + 未签会签人 + 抄送人（排除申请人）；标题「审批待办：…」 |
| 结果消息 | 接收人 = 申请人；「审批结果：…（已通过/已驳回）」 |
| 公告消息 | 接收人 = 全部启用账号（排除发布人），`bulk_create` 批量写入 |
| 入口 | 顶栏 ✉ + 未读数（`plugin_host.context_processors.notifications`）、侧栏「消息中心」、工作台「我的消息」最新 3 条 |
| 已读 | 单条 `/read/<id>/`（仅本人、仅站内链接跳转）、全部已读 POST；越权 404 |
| 停用降级 | 插件停用 → 菜单 / 顶栏 / 工作台入口隐藏；信号处理器仍安全跳过（表未迁移时 `logger.exception` 不外抛） |
| 测试 | 9 项：待办 / 结果 / 公告 fanout / 仅本人可见 / 已读跳转 / 越权 404 / 外链不跳 / 全部已读 / 停用隐藏 |

