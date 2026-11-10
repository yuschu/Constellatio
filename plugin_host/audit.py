"""审计字段自动填充（v1.7.8）：`pre_save` 统一写 created_by / updated_by。

规则（见 docs/plugin-dev-v178.md §2.4）：
- 新建且 `created_by` 为空 → 填当前用户（无上下文则 None），同时填 `updated_by`；
- 更新 → **只在有当前用户时**改 `updated_by`，不把已有值清空（后台任务不该抹掉线上操作人）；
- 显式传了 `created_by` → 尊重调用方，不覆盖；
- 无上下文（`manage.py shell` / 后台线程 / 信号内写入）→ 不报错。

只对 `AuditModel` 子类生效，其余模型早退。
"""

import logging

from django.db.models.signals import pre_save

from .current_user import get_current_user
from .models import AuditModel

logger = logging.getLogger('plugin_host')


def fill_audit_operator(sender, instance, **kwargs):
    """`pre_save` receiver：按上面的规则填操作人。"""
    if kwargs.get('raw'):
        # loaddata 等 fixture 导入：raw=True 时不要改数据（规范做法，且此时也没有上下文）
        return
    if not isinstance(instance, AuditModel):
        return
    user = get_current_user()
    if instance._state.adding:
        if instance.created_by_id is None and user is not None:
            instance.created_by = user
        if instance.updated_by_id is None:
            # updated_by 记「实际写这一行的人」：有请求上下文就用当前用户（显式传了
            # created_by=别人时也一样），没有上下文才回落到 created_by。
            instance.updated_by = user if user is not None else instance.created_by
        return
    if user is not None:
        instance.updated_by = user


def connect_audit_signals():
    """在 `apps.ready()` 调用；`dispatch_uid` 固定，避免 autoreload 重复连接。"""
    pre_save.connect(
        fill_audit_operator,
        dispatch_uid='plugin_host.audit.fill_audit_operator',
        weak=False,
    )
