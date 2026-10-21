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
    # 主题插件层（可插拔）
    'themes.risograph',
    # 业务插件层（全部可插拔；未实现阶段先注册，ready() 空跑无害）
    'plugins.auth',
    'plugins.user',
    'plugins.approval',
    'plugins.notice',
    'plugins.attendance',
    'plugins.blockchain',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
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
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 容器：向模板注入插件聚合菜单
                'plugin_host.context_processors.menus',
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
    {'app': 'plugins.notice', 'enabled': False},
    {'app': 'plugins.attendance', 'enabled': False},
    {'app': 'plugins.blockchain', 'enabled': False},
]

# 默认主题插件（新建 themes/<name>/ + 修改此项即换主题）
OA_THEME = 'themes.risograph'

# ---------------------------------------------------------------------------
# 密码校验 / 国际化 / 静态
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
