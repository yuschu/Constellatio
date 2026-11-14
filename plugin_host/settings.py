"""Constellatio 全局配置（Django 5.2）。

设计要点：
- AUTH_USER_MODEL 指向 user 插件（首次 migrate 前必须定，禁止后改）
- OA_PLUGINS / OA_THEME 驱动插件化（容器/主题/业务插件启停）
- 数据库从环境变量读取，未配置时回退 sqlite（本地开箱即用）；
  生产环境用 .env 提供 MySQL 连接（见部署文档）
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 安全
# ---------------------------------------------------------------------------
# v1.7.15 / 7.2：本地开发（DJANGO_DEBUG=1，默认）允许缺省 SECRET_KEY 以便开箱即用；
# **生产模式（DJANGO_DEBUG=0）缺 SECRET_KEY 直接拒绝启动**——硬编码默认值一旦随代码泄露，
# 会话签名与密码重置令牌全部可伪造。
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

_DEV_SECRET_KEY = 'django-insecure-3#=es$81&^2!rg&ybm3u9!r8u1@n-_j%a3r46^*0*6pj33c(k5'
_SECRET_KEY = os.environ.get('SECRET_KEY')
if not _SECRET_KEY:
    if DEBUG:
        _SECRET_KEY = _DEV_SECRET_KEY
    else:
        raise ImproperlyConfigured(
            '生产模式（DJANGO_DEBUG=0）必须提供 SECRET_KEY 环境变量。'
            '生成方式：python -c "import secrets;print(secrets.token_urlsafe(50))"；'
            '容器部署在部署配置中注入，不要提交到仓库。')
SECRET_KEY = _SECRET_KEY

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '*').split(',') if h.strip()]

# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django 内置
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 插件容器（唯一固定核心）
    'plugin_host',
    # 主题不再作为 Django app 加载；由 OA_THEME + theming.py 解析模板/静态目录
    # 业务插件层（全部可插拔；未实现阶段先注册，ready() 空跑无害）
    'plugins.auth',
    'plugins.user',
    'plugins.approval',
    'plugins.notice',
    'plugins.attendance',
    'plugins.blockchain',
    'plugins.workspace',
    'plugins.structure',
    'plugins.language',
    # v1.7.0：企业 SSO / 消息提醒
    'plugins.sso',
    'plugins.notify',
    # v2.0.0：对话式首页（A 阶段只做界面与骨架，不接模型调用）
    'plugins.assistant',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # v1.7.16：CSP（nonce 每请求一次）。放在最外层项目中间件之前——响应阶段自下而上，
    # 这样 ExceptionGuardMiddleware 渲染的 400/403 也会带上 CSP 头；硬 500 由 handler500 补。
    'plugin_host.csp.CspMiddleware',
    # v1.7.5：每个请求一个 8 位 request_id —— 放最外层之一，保证 500 响应也带 X-Request-Id
    'plugin_host.middleware.RequestIdMiddleware',
    # v1.7.5：异常分类（业务 400 / 越权 403 / 其它交默认 500）。必须在 RequestId 之内，
    # 这样兜底日志里的 request_id 一定已经存在。
    'plugin_host.middleware.ExceptionGuardMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # 容器内静态托管（无需 nginx）
    'django.contrib.sessions.middleware.SessionMiddleware',
    # 语言默认值（容器级，v1.5.7）：language 插件停用后仍沿用最后设置的语言
    'plugin_host.middleware.DefaultLanguageMiddleware',
    # 主题运行时切换（v1.5.8）：Cookie oa_theme → 当前请求主题
    'plugin_host.middleware.ThemeMiddleware',
    'django.middleware.common.CommonMiddleware',
    'plugin_host.middleware.PluginRouteGuardMiddleware',  # 插件运行时启停：停用即 404
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # v1.7.4：默认拦截 + 显式白名单。匿名请求在 process_view 阶段被拦下（跳 LOGIN_URL
    # 并带回 next），不再依赖逐个视图挂装饰器；匿名入口必须显式标注 @login_not_required。
    # 位置要求：必须在 AuthenticationMiddleware 之后（process_view 需要 request.user）。
    # v1.7.11：内置登录守卫的子类——匿名 + 要 JSON 时回 401 JSON（HTML 仍 302 + next）
    'plugin_host.middleware.JsonAwareLoginRequiredMiddleware',
    # v1.7.8：当前用户进 contextvar（审计字段 pre_save 自动填充用）；
    # 必须在 AuthenticationMiddleware 之后（request.user 可用），finally 复位防串号。
    'plugin_host.middleware.CurrentUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'plugin_host.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],   # v1.7.5：容器级模板（错误页 400/403/404/500）
        'APP_DIRS': False,      # v1.5.8：改为显式 loaders，支持按请求切换主题模板
        'OPTIONS': {
            'loaders': [
                # 主题模板（当前请求主题优先，未命中回退插件 app 模板）
                'plugin_host.theming.ThemeLoader',
                # v1.7.5：容器根 templates/（错误页）。ThemeLoader 只查主题目录，
                # 显式 loaders 下 DIRS 只有靠 filesystem.Loader 才生效，顺序放在主题之后。
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 容器：向模板注入插件聚合菜单 + 当前主题
                'plugin_host.context_processors.menus',
                'plugin_host.context_processors.themes',
                # 图表引擎（v1.6）：停用/未知时为 None，模板降级为表格
                'plugin_host.context_processors.charts',
                # v1.7.0：站内信未读数（插件停用 / 表未迁移时为 0）
                'plugin_host.context_processors.notifications',
                # v2.0：全站深浅模式（首页与业务页共用同一个 Cookie）
                'plugin_host.context_processors.color_mode',
                'plugin_host.context_processors.assets',
            ],
        },
    },
]

WSGI_APPLICATION = 'plugin_host.wsgi.application'

# ---------------------------------------------------------------------------
# 数据库（引擎可插拔：MySQL 默认生产 / sqlite 本地开发，一行切换）
# ---------------------------------------------------------------------------
if os.environ.get('DB_ENGINE', '').lower() == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('DB_NAME', 'constellatio'),
            'USER': os.environ.get('DB_USER', 'root'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# 缓存（v1.7.3：跨进程共享）
# ---------------------------------------------------------------------------
# 默认缓存必须是「所有 worker 共享」的存储，否则下面两处判定在多 worker 下不成立：
#   auth 登录失败限流（plugins/auth/views.py）——进程内计数会被 worker 分摊，5 次变 15 次
#   sso Ticket 防重放（plugins/sso/ticket.py）——进程内标记，同一 Ticket 可被不同 worker 各用一次
# DatabaseCache 的 add() 靠 cache_key 主键冲突实现「只有第一个写入者成功」，多进程语义成立，
# 无需引入 Redis。建表：容器由 entrypoint.sh 做，本地开发见 README，测试库见 TEST_RUNNER。
#
# OPTIONS['MAX_ENTRIES'] 必须远离默认的 300：DatabaseCache 超限时会 _cull（先删过期行，
# 仍超则按 cache_key 排序再删 1/CULL_FREQUENCY），**未过期的防重放标记也会被删掉**，
# 等于把重放窗口重新打开。500 人规模：限流键 ≤ 人数 + 5 分钟内 Ticket 标记数，万级留足余量。
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'constellatio_cache',
        'TIMEOUT': 900,                      # 与 LOGIN_FAIL_WINDOW 同口径（调用点各自显式传 timeout）
        'OPTIONS': {
            'MAX_ENTRIES': 10000,
            'CULL_FREQUENCY': 3,
        },
    },
}

# 测试库不会自动建缓存表（缺表时任何 cache 调用直接 OperationalError，实测）；
# 用自定义 runner 在 setup_databases 之后补 createcachetable，避免改测试绕过共享后端。
TEST_RUNNER = 'plugin_host.test_runner.CacheTableTestRunner'

# ---------------------------------------------------------------------------
# 认证与插件化配置
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'user.User'          # user 插件提供（首次 migrate 前必须定）
LOGIN_URL = '/plugins/auth/login/'
LOGOUT_REDIRECT_URL = '/plugins/auth/login/'

# ---------------------------------------------------------------------------
# 认证后端 Provider（v1.7.7）
# ---------------------------------------------------------------------------
# AUTHENTICATION_BACKENDS 是有序链：authenticate() 逐个尝试，第一个返回用户的生效。
# 加一行 = 多一种登录方式（dotted path）；ModelBackend 永远排最后，保证默认后端仍可用。
# 空列表也合法（只剩 ModelBackend）——否则新环境第一次 migrate 会死在校验里。
# 契约校验在 plugin_host.auth_backends.registry.validate_auth_backends（apps.ready 调用）。
OA_AUTH_BACKENDS = [
    'plugin_host.auth_backends.username_or_email.UsernameOrEmailBackend',
]
AUTHENTICATION_BACKENDS = [*OA_AUTH_BACKENDS, 'django.contrib.auth.backends.ModelBackend']

# 业务插件启停：enabled=False 即停用（路由/菜单/导航自动收敛）
OA_PLUGINS = [
    # v2.0.0：对话式首页放在首位——侧栏功能入口按此顺序渲染，
    # 「助手 / 看板」排在顶部功能入口区的前两格。
    # 停用后 index 自动回落原看板（/dashboard/ 始终可达）。
    {'app': 'plugins.assistant', 'enabled': True},
    {'app': 'plugins.auth', 'enabled': True},
    {'app': 'plugins.user', 'enabled': True},
    {'app': 'plugins.approval', 'enabled': True},
    {'app': 'plugins.notice', 'enabled': True},
    {'app': 'plugins.attendance', 'enabled': True},
    {'app': 'plugins.blockchain', 'enabled': True},
    {'app': 'plugins.workspace', 'enabled': True},
    {'app': 'plugins.structure', 'enabled': True},
    {'app': 'plugins.language', 'enabled': True},
    # v1.7.0
    {'app': 'plugins.sso', 'enabled': True},
    {'app': 'plugins.notify', 'enabled': True},
]

# ---------------------------------------------------------------------------
# 对话式首页的模型服务配置（部署时填写，不在安装包里内置任何模型）
# ---------------------------------------------------------------------------
# v2.3.0 A 阶段：OpenAI 兼容客户端只读这几项；base_url + model 都有值才启用输入区。
# 配置页保存的值存在 assistant_llm_settings（数据库优先），这里只做首次部署/回退兜底。
# api_key 可空（本地 ollama / llama.cpp 通常不校验）；超时与输出上限按最低档机器给默认值。
ASSISTANT_LLM_BASE_URL = os.environ.get('ASSISTANT_LLM_BASE_URL', '')
ASSISTANT_LLM_MODEL = os.environ.get('ASSISTANT_LLM_MODEL', '')
ASSISTANT_LLM_API_KEY = os.environ.get('ASSISTANT_LLM_API_KEY', '')
ASSISTANT_LLM_TIMEOUT = int(os.environ.get('ASSISTANT_LLM_TIMEOUT', '30') or 30)
ASSISTANT_LLM_MAX_TOKENS = int(os.environ.get('ASSISTANT_LLM_MAX_TOKENS', '1024') or 1024)

# ---------------------------------------------------------------------------
# v1.7.0 企业 SSO（签名 Ticket 网关）
# ---------------------------------------------------------------------------
# 网关使用同一共享密钥签发 ticket：base64url(payload).base64url(HMAC-SHA256)
# 生产环境务必通过环境变量覆盖默认值
SSO_SHARED_SECRET = os.environ.get('SSO_SHARED_SECRET', 'constellatio-sso-dev-secret')
SSO_TICKET_TTL = int(os.environ.get('SSO_TICKET_TTL', '300'))
SSO_AUTO_CREATE = os.environ.get('SSO_AUTO_CREATE', '1') == '1'

# 主题插件：themes/<key>/theme.json；OA_THEME 是默认/回退主题（v1.5.8 起支持运行时切换）
OA_THEME = os.environ.get('OA_THEME', 'corporate-clean')
THEME_COOKIE_AGE = 60 * 60 * 24 * 365   # 主题偏好 Cookie 1 年

# 图表引擎（v1.6）：charts/<key>/chart.json；空 / none / off 视为停用（页面降级为表格）
OA_CHARTS = os.environ.get('OA_CHARTS', 'echarts')

from plugin_host.charts import discover_charts  # noqa: E402
from plugin_host.theming import discover_themes, get_theme  # noqa: E402  (依赖 BASE_DIR)

_active_theme = get_theme(BASE_DIR, OA_THEME)   # 启动即校验 OA_THEME
# 每个已发现外观的静态资源都收集，运行时切换后 CSS 可用（路径按 themes/<key>/ 命名空间隔离）
STATICFILES_DIRS = [
    str(theme.static) for _, theme in sorted(discover_themes(BASE_DIR).items())
]
# 图表 Provider 的静态目录同样收集（ECharts 本地资源离线可用）
STATICFILES_DIRS += [str(meta.static) for meta in discover_charts(BASE_DIR).values()]

# ---------------------------------------------------------------------------
# 密码校验 / 国际化 / 静态
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGES = [
    ('zh-hans', '简体中文'),
    ('en', 'English'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
LANGUAGE_CODE = 'zh-hans'
# v1.5.7：语言偏好持久化 1 年（language 插件停用后仍沿用最后设置的语言）
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'   # collectstatic 产物（容器/gunicorn 服务）

# WhiteNoise 默认给未加哈希的静态文件 `max-age=60`，改完 CSS/JS 后连续刷新
# 仍可能读到旧文件，看上去像「容器没更新」。实测阶段关掉强缓存：
# 每次都带 ETag 回源，命中时 304，不影响正确性。
WHITENOISE_MAX_AGE = 0

# v1.5.14：审批附件（用章文件）落盘目录；下载统一走权限视图，不做公开静态目录
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# 日志（v1.7.5）
# ---------------------------------------------------------------------------
# 落点按进程模型分开（不同意容器也写文件）：
#   runserver / 单元测试（单进程）→ console + RotatingFileHandler（DJANGO_LOG_TO_FILE=1）
#   gunicorn 多 worker            → 只 console（docker 日志驱动收集）
# 原因：多进程各持一个句柄写同一个文件再 rotate，会出现「写进已改名的旧文件」「rotate 瞬间丢日志」
# 「两进程指向不同 inode」。日志轮转交给 docker / 宿主 logrotate 负责。
LOG_DIR = BASE_DIR / 'logs'
LOG_TO_FILE = os.environ.get('DJANGO_LOG_TO_FILE', '0') == '1'

_LOG_HANDLERS = ['console']
# 注意：logging.config.dictConfig 会把 handlers 里**定义过的每一个**都实例化，
# 哪怕没有 logger 引用它。所以文件 handler 必须按需拼接进字典，不能「定义但不使用」——
# 否则容器里即使 LOG_TO_FILE=0 也会打开 logs/constellatio.log。
_LOG_HANDLER_CONFIG = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
        'filters': ['request_id'],
    },
}
if LOG_TO_FILE:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_HANDLERS.append('file')
    _LOG_HANDLER_CONFIG['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'constellatio.log'),
        'maxBytes': 5 * 1024 * 1024,
        'backupCount': 5,
        'encoding': 'utf-8',
        'formatter': 'verbose',
        'filters': ['request_id'],
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    # request_id 只能由 filter 注入：直写 formatter 会让没有 request_id 的日志
    # （启动期 / manage.py）抛 KeyError，而 logging 默认吞 handler 错误 → 日志静默丢失。
    'filters': {
        'request_id': {'()': 'plugin_host.request_id.RequestIdFilter'},
    },
    'formatters': {
        'verbose': {
            'format': '%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s',
        },
    },
    'handlers': _LOG_HANDLER_CONFIG,
    'loggers': {
        'django': {'handlers': _LOG_HANDLERS, 'level': 'INFO', 'propagate': False},
        # 404 记 WARNING、500 记 ERROR（含 exc_info 全栈），排障主要看这条
        'django.request': {'handlers': _LOG_HANDLERS, 'level': 'WARNING', 'propagate': False},
        # 业务 / 容器日志保持 propagate=True：既进下面的 console/file handler，也继续向
        # root 传播——否则 `assertLogs()`（默认挂 root）在测试里收不到记录，
        # 依赖「handler 异常被记录」的既有用例会误报。root 不配 handler，所以不会重复输出。
        'plugins': {'handlers': _LOG_HANDLERS, 'level': 'INFO', 'propagate': True},
        'plugin_host': {'handlers': _LOG_HANDLERS, 'level': 'INFO', 'propagate': True},
    },
    # root 不配 handler（与 Django 默认行为一致）：未单独配置的库日志走 logging.lastResort
    'root': {'handlers': [], 'level': 'WARNING'},
}

# ---------------------------------------------------------------------------
# 传输安全（v1.7.1 / P1-13）
# ---------------------------------------------------------------------------
# 默认值优先保证「本地 runserver」与「docker compose 直连 8000 端口」可用：
# compose 没有 TLS 终止，直接开 SECURE_SSL_REDIRECT 会把所有请求跳进 https
# 而无法访问。生产部署应由前置反向代理终止 TLS，并显式打开下面的开关：
#   DJANGO_HTTPS=1        Cookie 仅 HTTPS 传输 + HSTS（默认关）
#   DJANGO_SSL_REDIRECT=1 全站 301 到 HTTPS（反代已跳转时不要重复开）
#   DJANGO_HSTS_SECONDS    HSTS 有效期，默认 31536000（1 年）
HTTPS_ENABLED = os.environ.get('DJANGO_HTTPS', '0') == '1'
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
# 反代转发 X-Forwarded-Proto 后，request.is_secure() 才为 True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SSL_REDIRECT', '0') == '1'
SECURE_HSTS_SECONDS = (
    int(os.environ.get('DJANGO_HSTS_SECONDS', '31536000')) if HTTPS_ENABLED else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(HTTPS_ENABLED)
SECURE_HSTS_PRELOAD = bool(HTTPS_ENABLED)
