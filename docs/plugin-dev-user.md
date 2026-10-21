# 插件开发文档：user 增强（部门软/硬删除 + 用户状态机 + 密码二次确认 + 权限层级）

> 关联插件：user（主体）、approval（会签审批扩展）、blockchain（上链）
> 版本规划：v1.2 · 文档版本：draft-01 · 2026-10-21
> 状态：**待确认后开发**

## 一、需求清单

1. 部门：新增**修改**；新增**删除**，分软/硬两档：
   - **软删除（停用）**：普通管理员（`user_manage`）即可操作，即时生效，留痕上链
   - **硬删除**：高危操作，不能直接删；发起【部门删除审批单】→ 全部有相应权限的管理员审批通过 → 才物理删除；删除动作本身也上链
2. 用户：**密码设置二次确认**（创建/编辑均需两次输入一致）
3. 用户状态：可**启用 / 禁用 / 冻结权限**：
   - 禁用前置条件：**先冻结权限** + **管理员审批通过**；admin（超管，0 号管理员）**直接禁用**（免审批）
   - 冻结权限：管理员直接操作（即时生效，可恢复）
   - 启用：管理员直接操作
4. **权限层级**：admin（超管）权限最高；其他任何用户（含普通管理员）都比 admin 低一级——普通管理员**不能**编辑/冻结/禁用/审批处理超管，超管不受普通管理员审批约束

## 二、权限层级规则（全插件生效）

| 层级 | 对象 | 判定 | 普通管理员对其可操作 |
|---|---|---|---|
| L0 最高 | admin 等超管 | `is_superuser=True` | ❌ 禁止（编辑/冻结/禁用/审批单处理均拒） |
| L1 | 普通管理员 | 有 `user_manage` | ✅（对 L2/L3） |
| L2/L3 | 员工等 | 普通用户 | ✅ |

- 实现：user 视图层统一守卫 `_guard_target(operator, target)` —— 目标为超管且操作者非超管 → redirect 工作台
- 超管操作免审批（直接禁用等）
- approval 会签审批人中**排除超管参与普通单会签**（审批人为有权限的非超管管理员）

## 三、数据模型变更

### 3.1 user 插件

**user_department 增字段**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| is_active | BOOL | NOT NULL, DEFAULT True | 软删除标志（False=已停用） |

**user_user 增字段**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| permission_frozen | BOOL | NOT NULL, DEFAULT False | 冻结权限标志（登录仍可，has_perm 恒 False） |

- 用户状态派生：`active`（is_active=True ∧ ¬frozen）/ `frozen`（is_active=True ∧ frozen）/ `disabled`（is_active=False）
- `User.has_perm()` 覆盖：`permission_frozen` 且非超管 → 直接 False（冻结即时生效，无需改任何权限分配）

**Meta.permissions 增补（user 插件）**

```
('user_disable_approve', '用户禁用审批')    # 会签审批人所需
('dept_delete_approve', '部门删除审批')      # 会签审批人所需
```

### 3.2 approval 插件（会签扩展，支撑部门删除/用户禁用审批单）

**approval_approval 增字段**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| target_type | VARCHAR(50) | NULL | 关联对象类型（department / user） |
| target_id | BIGINT | NULL | 关联对象 ID |

- `Approval.Type` 增：`DEPARTMENT_DELETE = 'dept_delete'`、`USER_DISABLE = 'user_disable'`（会签类：全部审批人通过才 approved）

**新增 approval_approvalsigner（会签人表）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | |
| approval | FK approval_approval | CASCADE | 审批单 |
| signer | FK user_user | PROTECT | 会签人 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending / approved / rejected |
| comment | TEXT | NULL | 个人意见 |
| acted_at | DATETIME | NULL | 表态时间 |

UNIQUE(approval, signer)

- **services.py 扩展**：
  - `create_consensus(approval_type, title, content, target_type, target_id, signer_ids, applicant)`：建单 + 全量 signer，status=pending
  - `sign_approve(approval, operator, comment)`：仅会签单；operator 的 signer → approved；**全部 approved → 单 approved + approval_finished（带 target_type/target_id/approval_type）**；任一 reject → 单 rejected + approval_finished(rejected)
- 审批人筛选（会签单）：**具备对应权限码（user_disable_approve / dept_delete_approve）的非超管管理员**（"全部有相应权限的管理员"）
- 详情/待办视图适配：会签单展示 signers 状态表；`_can_act` 增加"是 signer 且未表态"

### 3.3 信号扩展（plugin_host/signals.py）

```
department_delete_requested(department_id, requester_id)   # user → approval 发单
user_disable_requested(user_id, requester_id)              # user → approval 发单
department_soft_deleted(department_id, operator_id)        # user 软删后 → blockchain
department_hard_deleted(department_id, operator_id)        # user 硬删后 → blockchain
user_frozen(user_id, operator_id)                          # user 冻结后 → blockchain
user_enabled(user_id, operator_id)                         # user 启用后 → blockchain
user_disabled(user_id, operator_id)                        # user 禁用后 → blockchain
```

`approval_finished` 信号 kwargs **扩展**：`approval_type, target_type, target_id`（兼容既有订阅方 blockchain，向后兼容）

## 四、跨插件协作时序（零 import，只走信号）

### 4.1 部门硬删除

```
user 视图 POST 硬删
  → send department_delete_requested(department_id, requester_id)
approval 订阅：筛 user_disable 权限管理员 → create_consensus(type=dept_delete, target=department)
  各管理员在审批中心逐人 sign_approve
  全部通过 → approval_finished(approval_id, result=approved, approval_type=dept_delete, target_id=部门id)
user 订阅 approval_finished：dept_delete & approved → 物理删除 Department
  → send department_hard_deleted → blockchain 上链
```

### 4.2 用户禁用

```
普通管理员：先 POST 冻结（直接生效，user_frozen → 上链）→ 再 POST 发起禁用 → user_disable_requested → 会签 → approval_finished(user_disable, approved) → is_active=False → user_disabled → 上链
超管（admin）：POST 禁用 → 直接 is_active=False（免审批）→ user_disabled → 上链
```

### 4.3 软删除/启用/冻结（即时）

```
软删部门：POST → is_active=False → department_soft_deleted → 上链
启用用户：POST → is_active=True, frozen=False → user_enabled → 上链
冻结用户：POST → permission_frozen=True → user_frozen → 上链
```

### 4.4 blockchain 新增订阅

`department_soft_deleted / department_hard_deleted / user_frozen / user_enabled / user_disabled`

## 五、路由（user 插件增补）

| 路由 | 视图 | 权限 |
|---|---|---|
| `/plugins/user/departments/<int:dept_id>/edit/` | department_edit（改名/上级） | user_manage |
| `/plugins/user/departments/<int:dept_id>/soft-delete/` | department_soft_delete（POST） | user_manage |
| `/plugins/user/departments/<int:dept_id>/hard-delete/` | department_hard_delete_request（POST，发起审批单） | user_manage |
| `/plugins/user/users/<int:user_id>/freeze/` | user_freeze（POST） | user_manage + 层级守卫 |
| `/plugins/user/users/<int:user_id>/enable/` | user_enable（POST） | user_manage + 层级守卫 |
| `/plugins/user/users/<int:user_id>/disable/` | user_disable（POST：超管直禁 / 普通管理员走审批） | user_manage + 层级守卫 |

## 六、密码二次确认（forms.py）

- `UserForm` 增 `password_confirm` 字段（PasswordInput）
- 校验：password 非空时 `password == password_confirm`，否则表单错误
- 新建与编辑均生效；新建留空仍用默认密码（`constellatio123`），二次确认字段留空跳过

## 七、页面

- 部门列表：状态徽标（正常/已停用）+ 操作列（编辑 / 停用 / 删除审批单）；"已停用"部门默认隐藏，页头开关显示
- 用户列表：状态徽标（正常/已冻结/已禁用）+ 操作列（冻结 / 启用 / 禁用）；超管行操作列禁用提示"最高权限"
- 审批中心：会签单详情显示各会签人状态；待我审批含会签单

## 八、验收标准

1. 软删部门：列表立即消失（可切"显示已停用"），上链 `user:department_soft_deleted`，链校验通过
2. 硬删部门：发起审批单 → 全部有权限管理员通过 → 物理删除 → 上链 `user:department_hard_deleted`；未全通过（任一驳回）不删
3. 密码两次不一致 → 表单报错不保存；一致才生效
4. 冻结用户：立即无任何操作权限（has_perm 全 False），仍可登录
5. 禁用普通用户：普通管理员必须走"冻结 + 审批"两步；admin 直接禁用
6. 层级：普通管理员对 admin 的编辑/冻结/禁用/审批单操作全部被拒
7. 链完整性校验全程通过

## 九、测试计划

- user 单测：软删标志、has_perm 冻结短路、层级守卫、密码二次确认
- approval 单测：会签全通过→approved、任一驳回→rejected、signer 去重、非法重复表态
- 跨插件联调冒烟：硬删部门全链路（发单→逐人审批→删除→上链→校验）
- 回归：既有 approval 单审批人流程不受影响

## 十、改动文件清单

| 文件 | 动作 |
|---|---|
| `plugins/user/models.py` | Department.is_active / User.permission_frozen / 权限码增补 / has_perm 冻结短路 |
| `plugins/user/views.py` | 部门 edit/软删/硬删请求 + 用户 freeze/enable/disable + 层级守卫 `_guard_target` |
| `plugins/user/urls.py` / `forms.py` | 路由增补 / password_confirm |
| `plugins/user/apps.py` | 版本升 v1.2；订阅 approval_finished（dept_delete/user_disable 回调） |
| `plugins/approval/models.py` | Type 增两项 + target_type/target_id + ApprovalSigner |
| `plugins/approval/services.py` | create_consensus / sign_approve |
| `plugins/approval/views.py` / `urls.py` / `templates` | 会签展示与操作 |
| `plugins/approval/apps.py` | 订阅 department_delete_requested / user_disable_requested（建会签单） |
| `plugin_host/signals.py` | 新增 6 信号 + approval_finished kwargs 扩展 |
| `plugins/blockchain/apps.py` | 新增 5 订阅 |
