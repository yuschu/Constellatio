from django.apps import AppConfig


class RisographThemeConfig(AppConfig):
    """历史 AppConfig（v1.5 起不再加载）。

    v1.5 起主题由 themes/<key>/theme.json 发现，TEMPLATES.DIRS / STATICFILES_DIRS
    指向 OA_THEME 选中的主题；本文件保留仅作历史参考，不从 INSTALLED_APPS 加载。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "themes.risograph"
    # label 独立，避免与内置 / 其他 app 冲突
    label = "theme_risograph"
    verbose_name = "Risograph 印刷风主题（默认）"
