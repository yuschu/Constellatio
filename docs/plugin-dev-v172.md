# 插件开发文档：v1.7.2 公告极简化 + 考勤规则

> 关联插件：notice（公告流）、attendance（考勤规则）、user（权限等级注册表）、structure（角色权限模板）
> 版本：v1.7.2 · 文档日期：2026-10-27
> 状态：**✅ 已实现**（352 项测试全绿 + Docker 重建 + 页面冒烟）
> 说明：认证后端插件化由 v1.7.2 顺延至 **v1.7.3**

## 一、需求

1. **公告插件提易用性**：界面极简化，直接展示公告标题与内容，去掉冗余交互。
2. **考勤插件补规则配置能力**：新增「考勤规则」设置入口，上下班时间、宽限、工作日、补卡回溯可配置。

## 二、设计口径（契约）

### 2.1 公告（notice）

| 项 | 决策 |
|---|---|
| 信息架构 | **单列公告流**：一条公告一张卡，卡内依次为「标题（置顶徽标）→ 正文（`white-space:pre-wrap` 完整展示）→ 发布人 · 时间」 |
| 去除的交互 | `?notice=` 选中参数、左右双卡布局、切换公告下拉、已读人数/状态字段堆叠、「已读」弹窗、「返回列表」链接、页面内 `<script>` |
| 已读语义 | **进入列表即已读**：`AnnouncementRead.objects.bulk_create(..., ignore_conflicts=True)` 一次登记，刷新幂等，无需点击 |
| 已读统计 | 下沉为独立只读页 `/plugins/notice/<pk>/readers/`，仅 `notice_manage` 可见；列表页只留一个「已读 N 人」小链接，普通员工完全看不到入口 |
| 旧链接兼容 | `notice_detail`（`/plugins/notice/<pk>/`）302 到 `列表页#notice-<pk>`；每张卡带 `id="notice-<pk>"` 锚点 |
| 发布 | 语义不变（`notice_manage` + `notice_published` 信号），成功后回列表；权限守卫统一改用 `require_perm` |
| 数据 | **不新增字段、无迁移**，仍用 `notice_announcement` / `notice_announcementread` |

### 2.2 考勤规则（attendance）

| 项 | 决策 |
|---|---|
| 存储形态 | 新模型 `AttendanceRule`，**单例**（pk 固定 1，`save()` 强制），首次 `get_solo()` 时用默认值惰性创建；不预置数据行 |
| 默认值 | 09:00 / 18:00 / 宽限 0 / 工作日 `1,2,3,4,5` / 补卡回溯 7 天 —— **完全复现旧硬编码口径**，因此既有考勤测试零改动 |
| 判定来源 | `Attendance.compute_status()` 改为读 `AttendanceRule.get_solo()`：`late_threshold()` = 上班 + 迟到宽限，`early_threshold()` = 下班 − 早退宽限；补卡 > 缺卡 > 迟到 > 早退 > 正常的优先级不变 |
| 缓存 | `get_solo()` 带 60 秒进程内缓存 + `save()/delete()` 立即失效；**事务内（`in_atomic_block`）直读 DB**，避免 TestCase 回滚后串味（与插件开关缓存同一策略） |
| 工作日语义 | `workdays`（ISO 1–7）只用于 `is_workday()` 与看板口径展示，**不改变打卡状态判定**（周末打卡仍按时间判迟到/早退），避免语义膨胀 |
| 权限 | 新权限码 `attendance_rule_manage`，等级 **L1 系统管理**（改的是全员口径）；默认授予角色模板「系统管理员」，其他角色可由管理员在用户编辑页单独授予 |
| 入口 | 侧栏菜单「考勤规则」（`perm` 收敛）+ 考勤看板顶部「⚙ 考勤规则」按钮（按 `perms.attendance.attendance_rule_manage` 渲染） |
| 页面 | `/plugins/attendance/rules/`：单卡表单，`r-input` / `r-btn` 现有样式，无新增 CSS/JS；保存后页面内绿色徽标提示 |
| 校验 | 上下班时间先后、宽限 0–120、工作日 1–7 去重升序、补卡回溯 1–90；错误文案中文并全部进 i18n |
| 看板 | 「今日状态」卡展示当前口径（上班 / 下班 / 工作日）；「迟到次数」提示改用规则阈值（`{{ late }} 前签到为正常`） |

## 三、实现

### 3.1 公告

| 文件 | 改动 |
|---|---|
| `plugins/notice/views.py` | `notice_list` 改为「取 pk → 批量已读 → 注解 `read_count` → 显式排序（annotate 会丢 `Meta.ordering`）」；新增 `notice_readers`（`require_perm('notice_manage')`）；`notice_detail` 改锚点 302；`notice_create` 统一用 `require_perm` |
| `plugins/notice/urls.py` | 新增 `<int:pk>/readers/` |
| `plugins/notice/templates/notice/notice_list.html` | 重写为 69 行：公告流 + `readers_view` 分支（详情页与已读页复用同一模板，无新增模板文件） |

### 3.2 考勤规则

| 文件 | 改动 |
|---|---|
| `plugins/attendance/models.py` | 新增 `AttendanceRule`（8 字段 + `get_solo` / `workday_set` / `is_workday` / `late_threshold` / `early_threshold` / 缓存）；`compute_status()` 改读规则 |
| `plugins/attendance/forms.py`（新） | `AttendanceRuleForm`：字段校验 + 跨字段校验 + 规范化工序（workdays 去重升序） |
| `plugins/attendance/views.py` | 删除 `LATE_TIME` 常量；看板传入 `rule` 与阈值；新增 `attendance_rules`（GET 渲染 / POST 保存 / `updated_by` 记录） |
| `plugins/attendance/urls.py` | 新增 `rules/` |
| `plugins/attendance/apps.py` | 菜单新增「考勤规则」；`permissions` 补 `attendance_rule_manage`（版本号 0.6.0 → 0.7.0） |
| `plugins/attendance/templates/attendance/attendance_rules.html`（新） | 规则表单页 |
| `plugins/attendance/templates/attendance/attendance_dashboard.html` | 顶部规则入口按钮、今日口径展示、迟到提示改阈值 |
| `plugins/user/perms.py` | `PERMISSION_LEVELS['attendance_rule_manage'] = LEVEL_SYSTEM` |
| `plugins/structure/template.py` | `SYSTEM_ADMIN_PERMS` 追加 `attendance_rule_manage`（模板应用时授予系统管理员） |
| `locale/en/LC_MESSAGES/django.po` | 补 25 条英文翻译；替换 1 条废弃 msgid |

## 四、数据与迁移

- 新增迁移 `attendance/0005_attendancerule.py`：`CreateModel AttendanceRule` + `AlterModelOptions`（权限码）。**无数据回填**：规则行在首次访问（`get_solo()`）时按默认值创建，因此升级后无需人工初始化。
- notice 无模型改动、无迁移。

## 五、测试

全量 323 → **352**（+29）：

| 范围 | 项数 | 覆盖 |
|---|---|---|
| `plugins/notice/tests.py` | 11（原 6，重写 3、新增 5） | 三条公告标题 + 全文同屏、置顶在前、自动已读幂等、普通员工无已读入口且 readers 302、管理员 readers 200、旧详情链接锚点 302、发布成功跳转、无权限发布被拒 |
| `plugins/attendance/tests.py` | 55（+25） | 默认口径不变、改上班时间/迟到宽限/早退宽限后的判定、`workday_set` / `is_workday`、无权限 GET/POST、保存落库与 `updated_by`、非法输入（时间倒置 / 宽限越界 / 工作日非法 / 回溯越界）、缓存立即失效与非法 POST 不污染缓存 |

## 六、验收记录（2026-10-27）

| 项 | 结果 |
|---|---|
| `manage.py test` | **Ran 352 tests — OK** |
| `ruff check .` | All checks passed |
| `manage.py makemigrations --check --dry-run` | No changes detected（迁移已生成） |
| 公告页 | 单列展示标题与全文、置顶徽标、无 `<script>`、无切换下拉 |
| 考勤规则页 | 管理员可改并即时生效；非管理员 302 回首页 |
| 容器 | 重建后 `0005_attendancerule` 自动应用，页面 200 |

## 七、已知边界

1. **工作日不参与状态判定**：周末打卡仍按上下班时间判迟到/早退；「本月应出勤天数」暂未按工作日计算（需要时再引，避免与现有月度统计口径冲突）。
2. **规则只有一套**：不支持按部门/个人设置多套规则；如需分部门，可在 `AttendanceRule` 上加 `department` 外键并改造 `get_solo()`。
3. **补卡回溯天数暂未强校验**：`makeup_window_days` 已可配置并有默认值，但补卡视图目前不拒绝超过窗口的历史补卡（下一步接入时补测试）。
4. **公告已读是「进入即全部已读」**：不区分逐条已读；已读时间取服务端批量写入时刻。
5. 公告卡正文完整展开，超长公告会让页面变长 —— 需要折叠时再引「展开/收起」，当前按「直接展示内容」的需求不做折叠。
