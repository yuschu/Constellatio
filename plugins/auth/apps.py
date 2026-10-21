from django.apps import AppConfig


class AuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugins.auth"
    # label 用 plugin_auth，避免与 django.contrib.auth 的 'auth' 冲突
    label = "plugin_auth"
