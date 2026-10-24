"""Constellatio 全局配置（Django 5.2）。

设计要点：
- AUTH_USER_MODEL 指向 user 插件（首次 migrate 前必须定，禁止后改）
- OA_PLUGINS / OA_THEME 驱动插件化（容器/主题/业务插件启停）
- 数据库从环境变量读取，未配置时回退 sqlite（本地开箱即用）；
  生产环境用 .env 提供 MySQL 连接（见部署文档）
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 安全
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-3#=es$81&^2!rg&ybm3u9!r8u1@n-_j%a3r46^*0*6pj33c(k5')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
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
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'plugin_host.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': False,      # v1.5.8：改为显式 loaders，支持按请求切换主题模板
        'OPTIONS': {
            'loaders': [
                # 主题模板（当前请求主题优先，未命中回退插件 app 模板）
                'plugin_host.theming.ThemeLoader',
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
# 认证与插件化配置
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'user.User'          # user 插件提供（首次 migrate 前必须定）
LOGIN_URL = '/plugins/auth/login/'
LOGOUT_REDIRECT_URL = '/plugins/auth/login/'

# 业务插件启停：enabled=False 即停用（路由/菜单/导航自动收敛）
OA_PLUGINS = [
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
# 两套主题的静态资源都收集，运行时切换后 CSS 可用（路径按 themes/<key>/ 命名空间隔离）
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

# v1.5.14：审批附件（用章文件）落盘目录；下载统一走权限视图，不做公开静态目录
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
