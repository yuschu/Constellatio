# 插件开发文档：v1.7.0 企业 SSO 登录（签名 Ticket 网关）

> 关联：sso（新增）、auth（登录页入口）、plugin_host（信号 / 配置）
> 版本：v1.7.0 · 文档日期：2026-10-24
> 状态：**✅ 已实现并部署**（全量 259 项测试全绿）

## 一、目标

企业已统一身份认证时，员工从企业门户进入 Constellatio 无需再输账号密码：

1. 企业门户 / IdP 适配层使用共享密钥签发 **HMAC-SHA256 Ticket**；
2. 跳转 `https://<host>/plugins/sso/login/?ticket=<ticket>&next=/`；
3. 系统验签 → 关联账号（或按开关自动建号）→ 建立会话 → 回到目标页。

零第三方依赖，适配任何能签发 HMAC Ticket 的网关（企业微信/钉钉网关、Nginx+auth_request、Keycloak 适配层等）。

## 二、Ticket 契约

格式：`base64url(payload_json).base64url(HMAC-SHA256(secret, payload_b64))`

payload 字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `username` / `sub` | ✅ | 登录用户名（二者取一，优先 username） |
| `name` | 选填 | 姓名，写入 `User.last_name`（仅自动建号时） |
| `email` | 选填 | 邮箱（仅自动建号时） |
| `department` | 选填 | 部门名称；按启用部门名匹配后归属（仅自动建号时） |
| `iat` / `exp` | 自动 | 签发 / 过期时间（秒）；`exp` 必须晚于当前时间 |

校验：签名 `compare_digest`、`exp` 未过期、`iat` 不超前 60s、**同一 Ticket 只能使用一次**（TTL 内缓存占位防重放）、`next` 仅允许站内地址。

## 三、配置（环境变量 / settings）

| 配置 | 默认 | 说明 |
|---|---|---|
| `SSO_SHARED_SECRET` | `constellatio-sso-dev-secret` | 网关与系统共享密钥；**生产必须覆盖** |
| `SSO_TICKET_TTL` | `300` | Ticket 有效期（秒） |
| `SSO_AUTO_CREATE` | `1` | 用户不存在时自动建号（不可用密码，仅能 SSO 登录） |

插件可停用：`OA_PLUGINS` / 插件开关页 / `manage.py plugin_switch on|off sso`；停用后登录页入口隐藏、路由 404。

## 四、接口

| 路由 | 方法 | 说明 |
|---|---|---|
| `/plugins/sso/login/` | GET/POST | 门户跳转入口；无 Ticket 时渲染说明页 + 手工 Ticket 表单（联调） |
| `/plugins/sso/` | GET | 登录页按钮入口（说明页） |

登录成功发 `sso_login` 信号（`user_id / via='ticket' / auto_created`）；自动建号同时发 `user_created`（留痕插件可订阅）。

## 五、运维

```bash
# 为联调 / 测试签发 Ticket（打印到 stdout）
docker compose exec web python manage.py sso_ticket alice --name 张三 --ttl 120

# 企业网关签发示例（Python）
from plugins.sso.ticket import issue
url = '/plugins/sso/login/?ticket=' + issue({'username': 'alice', 'name': '张三'})
```

## 六、安全边界

- Ticket 走 HTTPS；共享密钥仅网关与系统持有，泄露等同登录凭据；
- 重放缓存为 Django 缓存（默认 LocMem，**多 worker 各自独立**）；生产建议配置共享缓存（Redis/Memcached）或缩短 TTL；
- 自动建号默认开启，建号用户无可用密码；如需严格管控设 `SSO_AUTO_CREATE=0`，账号由管理员预建；
- 禁用账号（`is_active=False`）拒绝登录；`permission_frozen` 用户可登录但无业务权限（沿用 RBAC）；
- `next` 做同源校验，禁止开放重定向。

## 七、测试（v1.7.0）

- Ticket 往返 / 篡改签名 / 过期 / 重放 / 畸形格式；
- 自动建号 + 登录、既有账号登录、禁用账号拒绝、非法 Ticket 错误页；
- 开放重定向拦截、`SSO_AUTO_CREATE=0` 不建号、管理命令签发可用 Ticket；
- 登录页 SSO 入口 `auth` 测试更新（13 项 SSO 测试）。
