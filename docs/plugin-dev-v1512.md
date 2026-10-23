# 插件开发文档：v1.5.12 角色成员弹窗修复 + 用户资料

> 关联插件：structure（角色弹窗 / 用户资料）、user（`User` 数据）
> 版本：v1.5.12 · 文档日期：2026-10-23
> 状态：**✅ 已实现**（169 项测试全绿 + Docker 重建 + 冒烟）

## 一、问题与需求

1. **Bug**：组织架构页点击「当前角色」卡片**没有弹窗**。
   根因：内联脚本写在内容区，而 `bootstrap.bundle.js` 在 `base.html` 末尾加载；脚本立即执行时 `window.bootstrap` 尚未定义，抛错导致点击事件从未绑定。
2. **需求**：查看角色成员后，可点击某个用户查看其资料。

## 二、修复与实现

| 项 | 决策 |
|---|---|
| 弹窗修复 | 脚本包进 `DOMContentLoaded`（bootstrap 已加载完成）并加 `if (!window.bootstrap) return;` 守卫；原有弹窗结构与数据不变 |
| 成员可点击 | 弹窗成员行改为 `<a href="/plugins/structure/user/<id>/">`，保留姓名 / 账号 / 部门 / 停用标记 |
| 用户资料 | 新增只读页 `/plugins/structure/user/<int:user_id>/`（`structure_view`）：姓名、账号、部门、角色、直属上级（可继续跳转）、状态（在职/停用/权限冻结）、邮箱、创建时间、直接下属数 |
| 其他入口 | 责任人清单的姓名列同样链接到用户资料 |
| 管理入口 | 浏览者具备 `user_manage` 时，资料页右上角显示「用户管理 →」（跳 `user:user_edit`） |
| 数据 | `role_rows.members` 增加 `url`（`reverse('structure:user_detail')`）；无新表、无迁移 |
| 权限 | `structure_view` 可看全员资料（与关系树同口径，页面级、无行级隔离）；未知用户 404 |

## 三、测试计划

1. 弹窗脚本改在 `DOMContentLoaded` 执行（模板标记）；
2. 角色成员 JSON 带 `url`；
3. 用户资料：`structure_view` 200 且含姓名/账号/邮箱/角色/上级；无权限 302；未知 id 404；
4. 「用户管理」入口仅 `user_manage` 可见；
5. 责任人清单姓名链接到资料页；
6. 既有 164 项不回归。

## 四、改动文件

| 文件 | 动作 |
|---|---|
| `plugins/structure/views.py` | 成员增加 `url`；新增 `structure_user_detail` |
| `plugins/structure/urls.py` | 新增 `user/<int:user_id>/` |
| `templates/structure/overview.html` | DOMContentLoaded 修复；成员行链接；清单姓名链接 |
| `templates/structure/user_detail.html` | 新增用户资料页 |
| `plugins/structure/tests.py` | 新增 5 项 |
| `locale/en/LC_MESSAGES/django.po` | 用户资料 / 基本信息 / 角色与联系方式 / 邮箱 / 创建时间 |
| `docs/plugin-dev-structure.md` / `roadmap.md` / `README.md` | 同步 |

## 五、验收结果（2026-10-23）

| 项 | 结果 |
|---|---|
| `manage.py check` | 0 issue |
| `makemigrations --check --dry-run` | No changes detected（无迁移） |
| 全量单测 | **169 项通过**（基线 164 + 新增 5） |
| Docker 重建 | `docker compose up -d --build` 成功，`constellatio-web-1` 已运行 |
| 弹窗修复冒烟 | 页面脚本含 `DOMContentLoaded` 与 `if (!window.bootstrap) return;`；成员 JSON 带 `"url": "/plugins/structure/user/<id>/"` |
| 用户资料冒烟 | 资料页 200：基本信息 / 邮箱 / 角色 / 直属上级跳转；管理员可见「用户管理 →」；`hr_qian`（无 structure_view）302 |
| 入口 | 弹窗成员行与责任人清单姓名均链接到资料页 |
