from django.apps import AppConfig


class RisographThemeConfig(AppConfig):
    """Risograph 印刷风主题插件（默认主题）。

    主题插件职责：提供模板基座（templates/）与静态资源（static/），
    通过 OA_THEME 配置切换；新增主题 = 新建 themes/<name>/ 并注册。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "themes.risograph"
    # label 独立，避免与内置 / 其他 app 冲突
    label = "theme_risograph"
    verbose_name = "Risograph 印刷风主题（默认）"
