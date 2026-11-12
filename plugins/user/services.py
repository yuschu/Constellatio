"""user 插件业务逻辑（v1.7.14）：用户状态机。

放这里而不是 views 的判据（完整判据见 docs/plugin-dev-v1714.md）：
- 需要**事务 / 权限阶梯 / 信号**这类业务规则；
- 同一逻辑可能被命令、回调、审批钩子复用；
- 需要能在 `manage.py shell` 里用**显式传参**验证（不读 `request`）。

视图只负责：取参数、调这里、把结果翻译成 HTTP 响应。
"""

from plugin_host.signals import user_disable_requested, user_disabled, user_status_changed

from .models import User


class StatusChangeDenied(PermissionError):
    """目标用户是超管且操作者不是超管（L0 保护）。"""


def can_change_status(operator, target):
    """权限阶梯：超管 L0 最高，其他任何用户不能对超管操作。"""
    return not (target.is_superuser and not operator.is_superuser)


def change_status(operator, target, action):
    """执行一次状态变更并发出对应信号；返回实际执行的语义名。

    返回值为 ``enabled`` / ``frozen`` / ``unfrozen`` / ``disabled`` / ``disable_requested``。
    `disable` 会按操作者身份分叉：超管直接禁用；普通管理员先冻结权限，再发起会签审批。

    直接调用（例如 shell）时若越权会抛 `StatusChangeDenied`——不会静默成功。
    """
    if not can_change_status(operator, target):
        raise StatusChangeDenied('不能操作超级管理员')

    operator_id = operator.pk
    if action == 'enable':
        target.is_active = True
        target.permission_frozen = False
        target.save(update_fields=['is_active', 'permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='enabled',
                                 operator_id=operator_id)
        return 'enabled'

    if action == 'freeze':
        target.permission_frozen = True
        target.save(update_fields=['permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='frozen',
                                 operator_id=operator_id)
        return 'frozen'

    if action == 'unfreeze':
        target.permission_frozen = False
        target.save(update_fields=['permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='unfrozen',
                                 operator_id=operator_id)
        return 'unfrozen'

    if action == 'disable':
        if operator.is_superuser:
            # 超管直接禁用：冻结权限 + 停用账号
            target.permission_frozen = True
            target.is_active = False
            target.save(update_fields=['permission_frozen', 'is_active', 'updated_at'])
            user_disabled.send(sender=User, user_id=target.pk, operator_id=operator_id)
            return 'disabled'

        # 普通管理员：先冻结权限（即时生效），再发起禁用会签审批
        target.permission_frozen = True
        target.save(update_fields=['permission_frozen', 'updated_at'])
        user_status_changed.send(sender=User, user_id=target.pk, status='frozen',
                                 operator_id=operator_id)
        display = target.last_name or target.username
        user_disable_requested.send(
            sender=User, user_id=target.pk, operator_id=operator_id,
            title=f'用户禁用审批：{display}',
            content=f'申请禁用用户「{display}」（ID:{target.pk}），需全部审批人通过后执行。')
        return 'disable_requested'

    raise ValueError(f'未知的状态操作: {action!r}')
