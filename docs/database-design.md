# 数据库设计文档（插件化）

> 项目：Constellatio —— 基于 Django 的企业办公自动化系统（全栈插件化）
> 文档版本：v1.7 · 2026-10-21（user 表已落地 v0.2；approval 两表已落地 v0.3；notice 两表已落地 v0.4；attendance 表已落地 v0.5；blockchain_record 已落地 v0.6——10 张业务表全部落地）
> 关联文档：tech-stack-and-architecture.md、constraints-and-acceptance.md、development-guide.md

---

## 一、设计原则（插件化）

1. **每插件独立数据域**：每个业务插件自带 models + migrations，独立建表，互不干扰
2. **表名插件前缀**：`<插件名>_<表名>`（Django 默认 app_label 前缀），杜绝跨插件重名
3. **跨插件禁止直查**：审批/公告/考勤需要用户数据时，只通过 user 插件暴露的 API 或 signals 获取，禁止直接查询其他插件的表
4. **FK 唯一例外**：业务插件允许外键引用 `settings.AUTH_USER_MODEL`（框架级配置引用，非插件间 import）
5. **引擎可插拔**：字段只使用 Django ORM 通用类型，不写 MySQL 私有类型；`utf8mb4`/`InnoDB` 等参数放 settings 的 `OPTIONS`，切换 MySQL↔sqlite↔postgres 只需改 `DATABASES`
6. **停用不删数据**：停用插件仅隐藏路由/导航，表与数据保留，可随时恢复启用
7. **审计字段统一**：所有业务表带 `created_at` / `updated_at`

## 二、插件-表映射

| 插件 | 表 | 归属 | 说明 |
|---|---|---|---|
| user | `user_department` | 业务 | 部门表 |
| user | `user_user`（AUTH_USER_MODEL） | 业务 | 用户表（AbstractUser 扩展） |
| user | `user_role` | 业务 | 角色表 |
| user | `user_user_roles` | 中间表 | 用户-角色 M2M |
| approval | `approval_approval` | 业务 | 审批单 |
| approval | `approval_approvalrecord` | 业务 | 审批留痕 |
| notice | `notice_announcement` | 业务 | 公告 |
| notice | `notice_announcementread` | 业务 | 公告已读 |
| attendance | `attendance_attendance` | 业务 | 考勤记录 |
| blockchain | `blockchain_record` | 业务 | 操作留痕链（哈希链，防篡改） |
| — | `auth_permission` 等 | 框架内置 | Django 自带（auth_group / django_session / django_migrations 等） |

业务插件共 **10 张表**；框架内置表不属于任何插件，由 Django 自动管理。

## 三、ER 关系总览

```
┌────────────┐ 1:N ┌──────────────────────┐
│ department │────▶│        user          │
└────────────┘     │ (AUTH_USER_MODEL)    │
                   └──┬───────┬───────┬───┘
                     M:N    1:N     1:N     1:N
                      │      │       │       │
            ┌─────────▼──┐  │       │       │
            │  role  ◀───┘  │       │       │
            │  (roles)     │       │       │
            └──┬──────────┘       │       │
             M:N                 │       │
              │                  │       │
     ┌────────▼────────┐  ┌──────▼──────┐
     │  auth_permission│  │  approval   │──1:N──▶ approval_record
     │  （框架内置）     │  └─────────────┘
     └─────────────────┘
    user 1:N notice_announcement 1:N notice_announcementread
    user 1:N attendance_attendance
    user 1:N blockchain_record（操作人 operator）
```

- 部门 1—N 用户；用户 M—N 角色；角色 M—N 权限（框架内置表）
- 用户 1—N 审批单；审批单 1—N 审批记录
- 用户 1—N 公告；公告 1—N 已读
- 用户 1—N 考勤记录

## 四、逐表设计

### 4.1 user 插件（plugins/user）

**user_department（部门表）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AUTO_INCREMENT | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | 部门名称 |
| parent_id | FK user_department.id | NULL, ON DELETE SET NULL | 上级部门 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

**user_user（用户表，AUTH_USER_MODEL）** —— 基于 AbstractUser 扩展

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| username | VARCHAR(150) | UNIQUE, NOT NULL | 登录名 |
| password | VARCHAR(128) | NOT NULL | Django 自动哈希 |
| last_name | VARCHAR(150) | NOT NULL | 中文姓名 |
| first_name | VARCHAR(150) | NULL | 备用 |
| email | VARCHAR(254) | NULL | 邮箱 |
| is_staff / is_active / is_superuser | BOOL | NOT NULL | Django 内置标志 |
| date_joined | DATETIME | NOT NULL | 注册时间 |
| department_id | FK user_department | NULL, ON DELETE SET NULL | 所属部门 |
| roles | M2M → user_role | 见中间表 | 用户角色 |
| created_at / updated_at | DATETIME | NOT NULL | 审计字段 |

**user_role（角色表）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | 角色名（如：管理员/主管/员工） |
| permissions | M2M → auth_permission | 框架内置表 | 角色权限 |
| created_at / updated_at | DATETIME | NOT NULL | 审计字段 |

**user_user_roles（用户-角色中间表，Django 自动生成）**

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PK |
| user_id | FK user_user | CASCADE |
| role_id | FK user_role | CASCADE |

UNIQUE(user_id, role_id)

### 4.2 approval 插件（plugins/approval）

**approval_approval（审批单）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| type | VARCHAR(20) | NOT NULL | leave(请假) / reimburse(报销) / stamp(用章) |
| title | VARCHAR(200) | NOT NULL | 审批标题 |
| content | TEXT | NOT NULL | 申请内容 |
| applicant_id | FK user_user | PROTECT | 申请人 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'draft' | draft / pending / approved / rejected |
| current_approver_id | FK user_user | NULL, ON DELETE SET NULL | 当前审批人 |
| created_at / updated_at | DATETIME | NOT NULL | 审计字段 |

索引：(status)、(applicant_id)

**approval_approvalrecord（审批留痕）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| approval_id | FK approval_approval | CASCADE | 所属审批单 |
| approver_id | FK user_user | PROTECT | 操作人 |
| action | VARCHAR(20) | NOT NULL | submit / approve / reject |
| comment | TEXT | NULL | 审批意见 |
| created_at | DATETIME | NOT NULL | 操作时间 |

索引：(approval_id)

### 4.3 notice 插件（plugins/notice）

**notice_announcement（公告）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| title | VARCHAR(200) | NOT NULL | 标题 |
| content | TEXT | NOT NULL | 内容 |
| publisher_id | FK user_user | PROTECT | 发布人 |
| is_top | BOOL | DEFAULT FALSE | 是否置顶 |
| created_at / updated_at | DATETIME | NOT NULL | 审计字段 |

索引：(is_top, created_at)

**notice_announcementread（公告已读）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| announcement_id | FK notice_announcement | CASCADE | 公告 |
| user_id | FK user_user | CASCADE | 读者 |
| read_at | DATETIME | NOT NULL | 已读时间 |

UNIQUE(announcement_id, user_id) —— 一人一篇只记一次

### 4.4 attendance 插件（plugins/attendance）

**attendance_attendance（考勤记录）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| user_id | FK user_user | CASCADE | 员工 |
| date | DATE | NOT NULL | 打卡日期 |
| check_in | DATETIME | NULL | 上班打卡 |
| check_out | DATETIME | NULL | 下班打卡 |
| created_at / updated_at | DATETIME | NOT NULL | 审计字段 |

UNIQUE(user_id, date) —— 一天一卡防重复

### 4.5 blockchain 插件（plugins/blockchain）

**blockchain_record（操作留痕链）** —— 哈希链防篡改审计

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK | 主键 |
| plugin | VARCHAR(50) | NOT NULL | 来源插件（approval / notice / attendance / user） |
| action | VARCHAR(50) | NOT NULL | 操作类型（approval_finished / attendance_checked / …） |
| target_type | VARCHAR(50) | NULL | 目标对象类型 |
| target_id | BIGINT | NULL | 目标对象 ID |
| operator_id | FK user_user | NULL, ON DELETE SET NULL | 操作人 |
| payload_hash | CHAR(64) | NOT NULL | 内容哈希（SHA-256） |
| prev_hash | CHAR(64) | NOT NULL | 前一条记录哈希（创世 = 64 个 0） |
| record_hash | CHAR(64) | NOT NULL, UNIQUE | 本条哈希 = SHA256(prev_hash + payload_hash + created_at) |
| created_at | DATETIME | NOT NULL | 上链时间 |

索引：(prev_hash) UNIQUE、(record_hash) UNIQUE、(plugin, action)

链式规则：每条记录按 `prev_hash → record_hash` 单向串链；校验时从创世逐条重算，任一条被篡改则后续全部断链报警。

### 4.6 框架内置表（不属于任何插件）

`django_migrations`、`auth_permission`、`auth_group`、`auth_group_permissions`、`django_content_type`、`django_session`、`django_admin_log` —— 由 Django 自动创建，不在插件职责内。

## 五、插件化数据约束

1. **引擎可插拔**：字段只用 Django ORM 通用类型；数据库专用参数（字符集/存储引擎）写在 settings `OPTIONS`，不写进模型
2. **分插件迁移**：`python manage.py makemigrations <插件名>` 独立生成，互不干扰
3. **停用保留数据**：插件从 `OA_PLUGINS` 停用后，表与数据保留，重新启用即恢复
4. **跨插件取数**：只通过 user 插件 API（如 `user.api.get_user(id)`）或 signals 获取，禁止跨表 JOIN
5. **FK 例外**：业务插件允许 FK `settings.AUTH_USER_MODEL`（框架级配置，非插件直接 import）
6. **删除策略**：业务主数据用 PROTECT / SET_NULL 防误删；记录类数据用 CASCADE 跟随清理

## 六、迁移管理

```bash
# 分插件生成迁移（按依赖顺序：先 user，再业务插件）
python manage.py makemigrations user
python manage.py makemigrations approval
python manage.py makemigrations notice
python manage.py makemigrations attendance
python manage.py makemigrations blockchain

# 应用全部迁移
python manage.py migrate

# 切换数据库引擎（演示可插拔）：只改 settings.DATABASES，无需改任何模型
#   ENGINE: django.db.backends.mysql / sqlite3 / postgresql
```

## 七、数据安全

- 密码：Django 自动 PBKDF2 哈希存储，禁止明文
- 审批意见/公告内容：正常存储，管理员可审计
- 删除审计：审批记录只增不改（追加式留痕），满足追溯要求
- 链式留痕：关键操作由 blockchain 插件写入哈希链（SHA-256 逐条串链），任何一条被篡改，其后全部校验失败——满足"不可篡改审计"要求
