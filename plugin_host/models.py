"""容器级抽象模型（v1.7.8）：审计字段统一。

`created_at` / `updated_at` 都声明为 **null=True**，两个理由：
1. 新增列时不能给历史行填迁移执行时间（那是伪造审计时间）——必须允许 NULL；
2. 模型已有非空同名时间列时，继承后会生成一次 `MODIFY ... NULL`（只放宽可空性，
   既有值不变），属于有意为之，比「为每个模型各写一套字段」更可维护。

操作人字段用 `related_name='+'`：不给用户模型加反向管理器，避免插件反向耦合。
`created_by` 的 verbose_name 是**「写入用户」**，与既有 `operator`（被留痕操作的业务主体）区分。
"""

from django.conf import settings
from django.db import models


class AuditModel(models.Model):
    """审计字段基类：`pre_save` 信号统一填 created_by / updated_by（见 plugin_host/audit.py）。"""

    created_at = models.DateTimeField('创建时间', auto_now_add=True, null=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+', verbose_name='写入用户')
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+', verbose_name='最后修改人')

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """部分更新也必须带上审计列（v1.7.8 收尾）。

        `Model.save(update_fields=[...])` 只写清单里的列；`pre_save` receiver 改的是
        `instance`，但 Django 传给 receiver 的 `update_fields` 是**值**不是引用，
        receiver 无法把列塞进 SQL 清单 —— 结果是 `updated_by` 只改在内存、DB 不写。
        实测生产代码有 20 处 `save(update_fields=...)` 全部踩这个坑，所以在基类统一并入，
        而不是让每个调用点各记一次（将来新增调用点还会漏）。
        """
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = list({*update_fields, 'updated_by', 'updated_at'})
        super().save(*args, **kwargs)
