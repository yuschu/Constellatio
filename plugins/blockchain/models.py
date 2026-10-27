"""blockchain 插件模型：操作留痕哈希链（防篡改审计）。

链式规则：record_hash = SHA256(prev_hash + payload_hash)。
校验时从创世逐条重算，任一条被篡改则后续全部断链报警。
"""

import hashlib

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils.translation import gettext_lazy as _

ACTION_LABELS = {
    'approval_finished': _('审批结束'),
    'notice_published': _('公告发布'),
    'attendance_checked': _('考勤打卡记录'),
    'user_created': _('用户创建'),
    'user_updated': _('用户更新'),
    'plugin_toggled': _('插件开关切换'),
    'dept_deleted': _('部门删除'),
    'dept_disabled': _('部门停用'),
    'dept_updated': _('部门修改'),
    'user_status_changed': _('用户状态变更'),
    'user_disabled': _('用户禁用'),
    'password_changed': _('密码变更'),
    'structure_applied': _('组织架构应用'),
}


class BlockchainRecord(models.Model):
    """操作留痕链表 blockchain_record（显式 db_table，对齐数据库设计）。"""

    plugin = models.CharField('来源插件', max_length=50)
    action = models.CharField('操作类型', max_length=50)
    target_type = models.CharField('目标类型', max_length=50, blank=True)
    target_id = models.BigIntegerField('目标 ID', null=True, blank=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='操作人')
    payload_hash = models.CharField('内容哈希', max_length=64)
    prev_hash = models.CharField('前链哈希', max_length=64, default='0' * 64)
    record_hash = models.CharField('本条哈希', max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'blockchain_record'
        verbose_name = '留痕记录'
        ordering = ['-id']
        # 插件权限码：迁移自动创建为 Permission
        permissions = [
            ('blockchain_view', '查看留痕'),
            ('blockchain_verify', '链完整性校验'),
        ]

    def __str__(self):
        return f'{self.plugin}:{self.action}#{self.id}'

    @property
    def plugin_title(self):
        """插件展示名：优先取注册表里的 gettext_lazy title，未知 key 回退原始值。"""
        from plugin_host.registry import PLUGIN_REGISTRY
        meta = PLUGIN_REGISTRY.get(self.plugin)
        return meta.title if meta else self.plugin

    @property
    def action_label(self):
        """动作展示名：信号动作映射为可翻译标签，未知动作回退原始值。"""
        return ACTION_LABELS.get(self.action, self.action)

    @classmethod
    def append(cls, plugin, action, payload, operator=None, **kw):
        """追加一条：record_hash = SHA256(prev_hash + payload_hash)。

        v1.7.x 并发加固：链尾在 ``select_for_update()`` 行锁内读取，
        “读链尾 → 算哈希 → 插入”在同一事务内完成，避免两个并发追加
        读到同一链尾而分叉。并发写入同一 payload 时 record_hash 可能撞上
        唯一键，此时回滚并重试一次（重试会重新读链尾，得到不同 prev）。
        """
        payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        for attempt in range(2):
            try:
                with transaction.atomic():
                    last = cls.objects.select_for_update().order_by('-id').first()
                    prev = last.record_hash if last else '0' * 64
                    record_hash = hashlib.sha256(
                        (prev + payload_hash).encode('utf-8')).hexdigest()
                    return cls.objects.create(
                        plugin=plugin, action=action, payload_hash=payload_hash,
                        prev_hash=prev, record_hash=record_hash,
                        operator=operator, **kw)
            except IntegrityError:
                # 唯一键冲突：并发同 payload 抢到了同一 record_hash，重试一次
                if attempt:
                    raise

    @classmethod
    def verify_chain(cls):
        """从创世逐条重算；任一条不符即被篡改，返回 (ok, 断裂处 id)。"""
        prev = '0' * 64
        for r in cls.objects.order_by('id'):
            if (r.prev_hash != prev or r.record_hash != hashlib.sha256(
                    (prev + r.payload_hash).encode('utf-8')).hexdigest()):
                return False, r.id
            prev = r.record_hash
        return True, None
