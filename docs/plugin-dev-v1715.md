# 插件开发文档：v1.7.15 Beta —— 私有化部署收口（离线资源 / 安全默认值 / 登出 POST / 覆盖率门槛）

> 关联：`themes/*/templates/{base,login}.html`、`plugin_host/static/vendor/bootstrap/`、`plugin_host/settings.py`、`plugins/auth/{views,urls}.py`、`.github/workflows/ci.yml`、`requirements-dev.txt`
> 版本：v1.7.15 · 文档日期：2026-11-12
> 状态：**✅ 已实现**（472 项测试 + 覆盖率 96%；见各节证据）
> 基线：tag `v1.7.14`（467 项测试）

## 7.1 离线可用：Bootstrap 本地化

**改前**：6 处引用 `cdn.jsdelivr.net`（4 处 `bootstrap.min.css` + 2 处 `bootstrap.bundle.min.js`，分布在
corporate-clean / risograph 两个主题的 `base.html` 与 `login.html`）。断网 → 登录页无样式。

**改后**：

| 文件 | 大小 | sha256（前 16 位） |
|---|---|---|
| `plugin_host/static/vendor/bootstrap/bootstrap.min.css` | 232 803 B | `3c8f27e6009ccfd7` |
| `plugin_host/static/vendor/bootstrap/bootstrap.bundle.min.js` | 80 721 B | `0833b2e9c3a26c25` |

- 放在 `plugin_host`（已注册 app）的 `static/` 下：`staticfiles` 的 `AppDirectoriesFinder` 自动收集，
  **不需要新增 `STATICFILES_DIRS`**（与 `charts/echarts/static/vendor/echarts.min.js` 同一做法）；
- 6 处全部改成 `{% static 'vendor/bootstrap/…' %}`，**没有保留 CDN 兜底**（禁止项 #1）；
- 两个主题都改了（禁止只改一个，有用例钉住）。

**为什么连 JS 也本地化**：6 处引用里 2 处是 `bootstrap.bundle.min.js`（下拉/折叠/提示等交互依赖它）。
只本地化 CSS 会让「断网样式完整、但交互全废」，验收里「样式完整」会掩盖这个问题。

**证据（容器实测）**：

```
登录页资源数 = 4 | 外网引用 = 0
/static/vendor/bootstrap/bootstrap.min.css              -> 200 232803 bytes
/static/themes/corporate-clean/css/corporate-clean.css  -> 200 11813 bytes
容器内 /app/staticfiles/vendor/bootstrap/：bootstrap.bundle.min.js 80721 / bootstrap.min.css 232803
```

> 真机冒烟（2026-11-12，维护者在真实浏览器执行）：**已通过**。
> 发版前本环境无浏览器，当时的等价证据是「渲染出的页面里 0 个外网引用 + 本地静态文件 200
> 且字节数与原 CDN 文件一致」——断网时浏览器只需访问同源 `/static/…`，不存在需要外网的分支。

新增 3 条用例 `plugin_host/tests_offline_assets.py`：登录页无外网引用、两个静态文件存在且大小达标
（防占位空文件）、两个主题的模板源码都不含 CDN 域名。

## 7.2 部署默认值：生产模式缺 SECRET_KEY 拒绝启动

**改前**：`settings.py` 里 `SECRET_KEY` 有硬编码默认值、`DEBUG` 默认 `'1'`、`ALLOWED_HOSTS` 默认 `'*'`。
硬编码密钥随代码泄露即可伪造会话签名与密码重置令牌。

**改后**（保留本地开箱即用，禁止项 #2）：

```python
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'          # 默认值保持 1（本地开发体验）
_SECRET_KEY = os.environ.get('SECRET_KEY')
if not _SECRET_KEY:
    if DEBUG:
        _SECRET_KEY = _DEV_SECRET_KEY                        # 仅开发模式用内置 key
    else:
        raise ImproperlyConfigured('生产模式（DJANGO_DEBUG=0）必须提供 SECRET_KEY 环境变量。…')
```

**证据 1：生产模式缺 SECRET_KEY 的启动报错（原文）**

```
django.core.exceptions.ImproperlyConfigured: 生产模式（DJANGO_DEBUG=0）必须提供 SECRET_KEY 环境变量。
生成方式：python -c "import secrets;print(secrets.token_urlsafe(50))"；容器部署在部署配置中注入，不要提交到仓库。
```

**证据 2：开发模式（默认）不受影响**

```
$ DJANGO_DEBUG=1 python manage.py check
System check identified no issues (0 silenced).
```

**证据 3：`check --deploy` 零告警**（CI 新增步骤，环境：`DJANGO_DEBUG=0` + 50 位随机 key +
`ALLOWED_HOSTS=example.com` + `DJANGO_HTTPS=1` + `DJANGO_SSL_REDIRECT=1` + `DJANGO_HSTS_SECONDS=31536000`）

```
$ python manage.py check --deploy
System check identified no issues (0 silenced).
```

> 注：若用弱 key（<50 字符或 `django-insecure-` 前缀）会命中 `security.W009`——CI 用的是真随机长 key。
> 本机实测过一次 W009，确认该检查在工作。

**未完成项（受阻，需你处理）**：`SECRET_KEY` 的必填标注要写进部署变量示例文件，但该文件被 DSH 凭据围栏
判为敏感路径，**读写均被拒绝**（不是权限问题，是策略）。请在该文件里把 SECRET_KEY 那两行改成：

```
# 必填（生产模式 DJANGO_DEBUG=0 下缺失会直接拒绝启动；v1.7.15）
# 生成：python -c "import secrets;print(secrets.token_urlsafe(50))"
SECRET_KEY=
```

### 7.2.1 compose 层也必须缺省即报错（P1，已修）

原先 `docker-compose.yml` 给 `SECRET_KEY` 一个默认值
（`${SECRET_KEY:-django-insecure-compose-default-change-me}`），与 settings 的硬要求**叠加后效果反转**：

1. settings 要求生产模式缺 key 就拒绝启动；
2. compose 却保证 key 永远有值（且是**写在公开仓库里**的固定串）；
3. 于是唯一实际的部署路径上这条硬要求永不触发——它只挡住了裸跑 `manage.py` 的本机调试，
   而生产部署反而拿了一个所有读者都知道的密钥，session 与密码重置令牌可被伪造；
4. 比「根本没有硬要求」更糟：没有要求时用户还可能自己生成随机值。

`check --deploy` **覆盖不到**这一条（compose 的 env 不参与 Django system check），所以零告警在这里会
带来假安全感。

改法：

```yaml
SECRET_KEY: ${SECRET_KEY:?SECRET_KEY 必须设置（生产模式拒绝使用默认值；生成方式见部署文档）}
```

**证据 1：`docker compose config` 缺 key 时的报错原文**

```
error while interpolating services.web.environment.SECRET_KEY: required variable SECRET_KEY is
missing a value: SECRET_KEY 必须设置（生产模式拒绝使用默认值；生成方式见部署文档）
exit=1
```

**证据 2：`docker compose up -d` 缺 key 时直接退出（不会起半套服务）**

```
error while interpolating services.web.environment.SECRET_KEY: … (同上)
exit=1
```

**证据 3：提供 key 后解析通过**

```
$ SECRET_KEY=<50 位随机> docker compose config
      SECRET_KEY: AHmMk2qSrAFpVZJs28TsvO69K-0Dr8uD7sQuwe7Jf70uOKRD0D_xehJ6YIVajNOCjao
```

> 影响：本机/CI 起容器现在必须显式给 `SECRET_KEY`（`export`、行内前缀、或部署变量文件）。
> 这是**期望的失败方式**——与「私有化部署收口」同一口径；退路成本一行命令。

## 7.3 登出改 POST

**改前**：`logout_view` 是 GET，导航是 `<a href="/plugins/auth/logout/">`。第三方页面一张
`<img src="/plugins/auth/logout/">` 就能把人踢下线（CSRF 对 GET 天然无效）。

**改后**：

- `logout_view` 加 `@require_POST`（`@login_not_required` 保留在外层）；
- 两个主题 `base.html` 的登出入口改成 `<form method="post">` + `{% csrf_token %}` + `<button>`。

**证据：新增 2 条用例（这是全仓第一次覆盖登出）**

```
$ python manage.py test plugins.auth.tests_logout
Ran 2 tests

test_get_logout_is_rejected_and_session_kept   GET → 405，会话仍有效，受控页仍 200
test_post_logout_clears_session                POST → 302，session 无 _auth_user_id，再访问受控页 302 到登录页
```

> 事实补充确认：改前全仓 grep `logout` 只命中定义处与 `urls`，**零测试覆盖**——所以本次不是「测试跟着改」，
> 而是补上了原本不存在的护栏。

## 7.4 覆盖率门槛

**实测（`coverage run --source=plugins,plugin_host manage.py test`）**：

```
TOTAL   8020 statements   292 missed   96%
```

门槛按「当前值 - 2」设为 **94**（CI：`coverage report --fail-under=94`）。
`requirements-dev.txt` 固定 `coverage==7.6.10`（CI 与本地同版本，避免口径漂移）。

本地实测门槛生效：

```
$ coverage report --fail-under=94
TOTAL   8020   292   96%
exit=0
```

## 四、验收汇总

| 项 | 证据 |
|---|---|
| 7.1 离线 | 登录页 0 个外网引用；本地 CSS 200 / 232 803 B；容器 staticfiles 已收集；3 条用例 |
| 7.2 默认值 | 生产缺 key → `ImproperlyConfigured` 原文；开发模式无影响；`check --deploy` 零告警 |
| 7.3 登出 | 405 / 302+session 失效 两条用例输出；两个主题改 form |
| 7.4 覆盖率 | 96%（8020/292），门槛 94，CI 步骤 |

门禁：`ruff` / `check` / 全量 **472 项 OK**。

## 五、不做 / 已知边界

- 不改 `DEBUG` 默认值为 0（禁止项 #2）：本地 `runserver` 开箱即用靠它。
- 不保留 CDN 兜底（禁止项 #1）：断网时兜底分支等于没有。
- ~~不动 `docker-compose.yml` 的 SECRET_KEY 默认值~~ —— P1 已改为缺省即报错（见 §7.2.1）。
- 不做前端构建/打包（bootstrap 直接以原文件进 static）。

## 六、待办

1. ~~发版前真机冒烟（v1.7.12 遗留 + v1.7.15 / 7.1 的断网截图）~~ —— 2026-11-12 真机验证通过。
2. 部署变量示例文件的 SECRET_KEY 必填标注 —— 已由外部复核代为修改（该路径被本环境的凭据围栏
   挡住，我读不到内容；**以仓库为准，不要重复改**）。
3. ~~`docker-compose.yml` 的 SECRET_KEY 默认值~~ —— 已在 §7.2.1 改为缺省报错（P1 修复）。
