"""v1.7.14：user 插件 service 层单测（状态机 + 超管保护 + 会签分支）。

这些用例**不建 HTTP 请求**：直接调 `plugins.user.services`，证明
「service 可脱离 request 调用」这条判据成立。
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from . import services

User = get_user_model()


class UserStatusServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('svc_admin', '', 'pw')
        cls.manager = User.objects.create_user('svc_mgr', password='pw')
        cls.member = User.objects.create_user('svc_member', password='pw', last_name='员工甲')

    def test_superuser_can_disable_target_directly(self):
        """超管禁用：冻结权限 + 停用账号，发 user_disabled，返回 disabled。"""
        with mock.patch.object(services, 'user_disabled') as disabled, \
                mock.patch.object(services, 'user_status_changed') as status_changed:
            result = services.change_status(self.admin, self.member, 'disable')

        self.assertEqual(result, 'disabled')
        disabled.send.assert_called_once()
        status_changed.send.assert_not_called()
        self.member.refresh_from_db()
        self.assertTrue(self.member.permission_frozen)
        self.assertFalse(self.member.is_active)

    def test_manager_disable_goes_through_counter_signature(self):
        """普通管理员禁用：只冻结权限（账号仍启用），并发起会签审批。"""
        with mock.patch.object(services, 'user_disable_requested') as requested, \
                mock.patch.object(services, 'user_disabled') as disabled:
            result = services.change_status(self.manager, self.member, 'disable')

        self.assertEqual(result, 'disable_requested')
        requested.send.assert_called_once()
        disabled.send.assert_not_called()          # 未真正禁用
        self.member.refresh_from_db()
        self.assertTrue(self.member.permission_frozen)
        self.assertTrue(self.member.is_active)

    def test_freeze_and_unfreeze_are_idempotent(self):
        self.assertEqual(services.change_status(self.manager, self.member, 'freeze'), 'frozen')
        self.assertEqual(services.change_status(self.manager, self.member, 'freeze'), 'frozen')
        self.member.refresh_from_db()
        self.assertTrue(self.member.permission_frozen)

        self.assertEqual(services.change_status(self.manager, self.member, 'unfreeze'), 'unfrozen')
        self.member.refresh_from_db()
        self.assertFalse(self.member.permission_frozen)

    def test_enable_clears_frozen_and_reactivates(self):
        self.member.permission_frozen = True
        self.member.is_active = False
        self.member.save(update_fields=['permission_frozen', 'is_active'])

        self.assertEqual(services.change_status(self.manager, self.member, 'enable'), 'enabled')
        self.member.refresh_from_db()
        self.assertFalse(self.member.permission_frozen)
        self.assertTrue(self.member.is_active)

    def test_non_superuser_cannot_touch_superuser(self):
        """超管 L0 保护：非超管对超管操作要抛 StatusChangeDenied，且目标未被修改。"""
        target = User.objects.create_superuser('svc_admin2', '', 'pw')
        self.assertFalse(services.can_change_status(self.manager, target))
        with self.assertRaises(services.StatusChangeDenied):
            services.change_status(self.manager, target, 'disable')
        target.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(target.permission_frozen)

    def test_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            services.change_status(self.manager, self.member, 'reboot')
