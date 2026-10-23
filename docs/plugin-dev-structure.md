# 插件开发文档：structure（职能制公司架构模板，含全部角色与用户模板）

> 关联插件：user（写入部门/角色/用户）、blockchain（应用动作上链）
> 版本规划：v1.3 · 文档版本：v1.3 · 2026-10-21
> 状态：**✅ 已实现并跑通**（6 项单测全绿 + HTTP 冒烟：总览渲染、20 部门/31 角色/31 用户幂等应用、授权开关、structure_applied 上链、链校验通过、开关页可停用）

## 一、需求

根据**职能制公司架构**提供"组织结构模板"插件：
- 预置完整部门树（职能制）
- 预置全部职能角色
- 预置用户模板（演示账号：姓名/部门/角色/初始密码），一键应用初始化
- 应用动作留痕上链

## 二、设计要点

| 项 | 决策 |
|---|---|
| 形态 | 新插件 `plugins/structure`（模板能力插件化） |
| 存储 | **不新建业务表**：模板定义在 `structure/template.py` 代码常量（部门树/角色清单/用户模板清单），可扩展；建 `structure_structurerecord` 表（记录最近一次应用：时间/操作人/新增计数）承载权限码 + 应用留痕 |
| 幂等 | 应用 = **只创建缺失，不覆盖已有**（按 name 查部门/角色，按 username 查用户；已存在跳过）；可重复应用 |
| 权限 | 查看架构总览：登录用户即可；应用结构：`structure_manage` 权限码 |
| 权限层级 | 应用仅创建普通用户/角色/部门，**不触碰超管**；与 user 插件层级规则一致（操作目标永不涉及 admin） |
| 角色权限 | 模板角色为**身份角色（默认空权限）**，管理权限由管理员按需分配；应用时提供选项 `grant_manager_perms`（默认关，开启则"经理"类角色授予 `user_manage`） |
| 用户模板密码 | 统一 `constellatio123`（与 user 插件默认密码一致），应用后可在用户管理修改 |
| 上链 | 应用完成后发 `structure_applied` 信号 → blockchain 订阅（action='structure_applied'，payload=新增计数统计） |
| 跨插件 | 零 import：`apps.get_model('user','Department'/'Role'/'User')` 动态获取 |
| 菜单 | 侧栏"组织架构"（总览） + "应用结构"入口；home 不加重入口卡（避免拥挤） |

## 三、职能制模板定义（template.py 常量）

### 3.1 部门树（职能制，12 个一级部门 + 8 个二级，共 20 个）

```
总裁办
├─ 总经理办公室
人力资源部
├─ 招聘组 / 培训组 / 薪酬绩效组
财务部
市场部
销售部
研发部
├─ 产品组 / 设计组 / 测试组
运营部
客服部
行政部
法务部
采购部
信息技术部
├─ 运维组
```

### 3.2 角色清单（身份角色，默认空权限）

- 总经理
- 部门经理：人力资源经理 / 财务经理 / 市场经理 / 销售经理 / 研发经理 / 运营经理 / 客服经理 / 行政经理 / 法务经理 / 采购经理 / IT经理
- 专员/专业岗：HRBP / 招聘专员 / 培训专员 / 薪酬绩效专员 / 会计 / 出纳 / 市场专员 / 销售专员 / 产品经理 / UI设计师 / 研发工程师 / 测试工程师 / 运营专员 / 客服专员 / 行政专员 / 法务专员 / 采购专员 / IT运维工程师 / 系统管理员

### 3.3 用户模板清单（31 个，账号=拼音缩写，密码 constellatio123）

| 账号 | 姓名 | 部门 | 角色 |
|---|---|---|---|
| gm_zhang | 张总 | 总裁办 | 总经理 |
| hr_wang | 王经理 | 人力资源部 | 人力资源经理 |
| hr_zhao | 赵HR | 人力资源部·招聘组 | HRBP |
| hr_qian | 钱招聘 | 人力资源部·招聘组 | 招聘专员 |
| hr_sun | 孙培训 | 人力资源部·培训组 | 培训专员 |
| hr_li | 李薪酬 | 人力资源部·薪酬绩效组 | 薪酬绩效专员 |
| fin_zheng | 郑经理 | 财务部 | 财务经理 |
| fin_wu | 吴会计 | 财务部 | 会计 |
| fin_chen | 陈出纳 | 财务部 | 出纳 |
| mkt_feng | 冯经理 | 市场部 | 市场经理 |
| mkt_chu | 褚市场 | 市场部 | 市场专员 |
| sal_wei | 卫经理 | 销售部 | 销售经理 |
| sal_jiang | 蒋销售 | 销售部 | 销售专员 |
| rd_han | 韩经理 | 研发部 | 研发经理 |
| rd_yang | 杨产品 | 研发部·产品组 | 产品经理 |
| rd_zhu | 朱研发 | 研发部 | 研发工程师 |
| rd_yan | 闫测试 | 研发部·测试组 | 测试工程师 |
| rd_qin | 秦设计 | 研发部·设计组 | UI设计师 |
| ops_lin | 林经理 | 运营部 | 运营经理 |
| ops_he | 何运营 | 运营部 | 运营专员 |
| cs_xu | 徐经理 | 客服部 | 客服经理 |
| cs_gao | 高客服 | 客服部 | 客服专员 |
| adm_huang | 黄经理 | 行政部 | 行政经理 |
| adm_liang | 梁行政 | 行政部 | 行政专员 |
| legal_liu | 刘经理 | 法务部 | 法务经理 |
| legal_shi | 施法务 | 法务部 | 法务专员 |
| pur_du | 杜经理 | 采购部 | 采购经理 |
| pur_xiao | 肖采购 | 采购部 | 采购专员 |
| it_cai | 蔡经理 | 信息技术部 | IT经理 |
| it_luo | 罗运维 | 信息技术部·运维组 | IT运维工程师 |
| it_zhou | 周系统 | 信息技术部 | 系统管理员 |

## 四、接口 / 路由

| 路由 | 视图 | 权限 | 说明 |
|---|---|---|---|
| `/plugins/structure/` | structure_overview | 登录可见 | 架构总览：部门树 + 角色清单 + 用户模板分组预览（只读） |
| `/plugins/structure/apply/` | structure_apply（POST） | structure_manage | 幂等应用：创建缺失部门/角色/用户；返回统计；上链 |

## 五、数据模型

**structure_structurerecord（结构应用记录）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | |
| applied_by | FK user_user | PROTECT | 操作人 |
| dept_created | INT | NOT NULL | 新增部门数 |
| role_created | INT | NOT NULL | 新增角色数 |
| user_created | INT | NOT NULL | 新增用户数 |
| grant_manager_perms | BOOL | NOT NULL, DEFAULT False | 本次是否授经理管理权限 |
| applied_at | DATETIME | auto_now_add | 应用时间 |

Meta.permissions：`('structure_manage', '结构模板应用')`

## 六、信号

```
structure_applied(applied_by_id, dept_created, role_created, user_created)  # structure → blockchain
```

## 七、验收标准

1. 总览页渲染：部门树 12 一级（含二级）、角色 25+、用户模板 31 条，分组正确
2. 应用后：部门/角色/用户全部创建，归属正确（用户挂部门+角色），密码可登录
3. 重复应用幂等：新增计数为 0，不重复创建
4. 无 `structure_manage` 权限用户：总览可见、apply 被拒（redirect）
5. 上链含 `structure_applied` 且链校验通过
6. 与既有数据共存：不覆盖不删除任何既有部门/角色/用户；admin 不受影响

## 八、测试计划

- 单测：模板完整性（数量/名称校验）、幂等应用、归属正确、权限守卫、manager 授权开关
- 冒烟：总览渲染 → apply → 用户管理可见新用户 → 重复 apply 计数 0 → 留痕链校验

## 九、改动文件清单

| 文件 | 动作 |
|---|---|
| `plugins/structure/`（apps/models/services/views/urls/template/tests/migrations/templates） | 新增 |
| `plugin_host/settings.py` | INSTALLED_APPS + OA_PLUGINS 增 structure |
| `plugin_host/signals.py` | 增 structure_applied |
| `plugins/blockchain/apps.py` | 增订阅 structure_applied |
| `README.md` / `docs/project-overview.md` 等 | 特性 + 待办同步 |

## 十、v1.5.4 增补：角色权限模板

### 10.1 模板权限

- `template.py` 新增 `ROLE_PERMISSIONS`（角色 → 权限码集合）：
  - 总经理：L2 管理岗全套 + `user_manage`；
  - 11 个部门经理：`approval_view` `approval_approve` `attendance_report_view` `notice_manage` `blockchain_view` `structure_view`；
  - HRBP：`approval_view` `attendance_report_view` `structure_view`；
  - 系统管理员：L1 全套 + L2 只读/审批 + `blockchain_verify`；
  - 其他专员/工程师：`approval_view`。
- 全员基线（考勤打卡 / 公告浏览）由 user 插件自动生效，不写入角色权限。

### 10.2 应用与升级

- `apply_structure()`：创建缺失部门/角色/用户后，按 `ROLE_PERMISSIONS` **幂等补齐**角色权限（只增不减，不覆盖人工调整）；
- `grant_manager_perms` 保留为**默认关闭**的选项：勾选时额外给经理类角色 `user_manage`（L1），避免部门经理默认越级；
- 老库升级执行 `python manage.py grant_role_perms`（支持 `--dry-run`），为既有 31 个角色补齐模板权限；加 `--revoke-manager-perms` 可收回部门经理遗留的 L1 `user_manage`（总经理/系统管理员保留）；
- 总览页准入改为 `structure_view`，应用仍为 `structure_manage`；总览角色徽标显示模板权限数。

### 10.3 测试

- 角色模板授予（经理含签到详情、专员不含）、幂等只增不减、`grant_role_perms` 命令、总览准入。

## 十一、v1.5.5 增补：直属上级映射

- `template.py` 新增 `LEADER_OF`（账号 → 上级账号）：部门经理 → 总经理，组内成员 → 部门负责人；总经理无上级。
- `apply_structure()` 在创建/幂等应用后补齐上级（**只补空，不覆盖人工调整**）；`manage.py grant_role_perms --seed-leaders` 用于老库一次性补齐。
- 该映射供审批「审批人留空时自动指派直属上级」与「抄送审批人上级」使用。
- 测试：组员上级为部门经理、经理上级为总经理、总经理无上级、重复应用不覆盖人工调整。

## 十二、v1.5.6 增补：用户关系树（责任划分）

### 12.1 定位

总览页从「模板预览」补上「真实账号的关系树」，用于责任划分：谁向谁汇报、每位责任人的直接下属与含下级规模。

### 12.2 口径（详见 `docs/plugin-dev-v156.md`）

- **数据源**：真实 `user.User`，不改模板常量；上级唯一来源 `User.leader`（不新增表、无迁移）。
- **树**：无上级为根；`A→B→A` 与自环按「汇报环」处理——环上节点提为根并标 `汇报环`，环内边断开，页面不递归、节点不重复；环外下属仍挂在其上级下。
- **停用账号**：保留在树中并标「停用」，上级停用不拆树；上级被删（`SET_NULL`）自然成为根。
- **计数**：直接下属 = `leader` 指向本人的账号数；含下级合计 = 子树账号数（不含本人）。
- **权限**：沿用总览 `structure_view`，不做行级数据权限；无新路由、无新菜单。

### 12.3 实现落点

| 文件 | 内容 |
|---|---|
| `plugins/structure/hierarchy.py` | `build_user_tree()` → `roots / rows / stats`；环检测（迭代 DFS 染色） |
| `plugins/structure/views.py` | 总览注入 `org_roots / org_rows / org_stats`；修复 `users_by_dept` 未注入缺陷 |
| `templates/structure/overview.html` | 「用户关系树（责任划分）」统计 + 树 + 「责任人清单」表 |
| `templates/structure/_tree_node.html` | 递归节点片段（角色徽标 / 直接下属 / 汇报环 / 停用） |

### 12.4 测试

树层级与计数、多根、成环（含自环）不递归不重复、停用保留、总览渲染与 `structure_view` 守卫、用户模板分组回归。
