"""user 插件 v1.2 测试：部门软/硬删、用户状态机、权限层级、密码二次确认。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from plugin_host import signals as bus

from .forms import UserForm
from .models import Department, Role, User

P = Permission.objects


class DepartmentV12Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin', '', 'adminpass')
        cls.dept = Department.objects.create(name='研发部')

    def test_soft_delete_marks_inactive_and_signals(self):
        """软删：is_active=False + dept_disabled 信号。"""
        got = []
        bus.dept_disabled.connect(lambda sender, **kw: got.append(kw), weak=False)
        self.client.force_login(self.admin)
        self.client.post(reverse('user:department_list'),
                         {'action': 'soft_delete', 'dept_id': self.dept.pk})
        self.dept.refresh_from_db()
        self.assertFalse(self.dept.is_active)
        self.assertEqual(got[-1]['dept_id'], self.dept.pk)

    def test_hard_delete_with_members_blocked(self):
        """硬删：有成员时拒绝并提示。"""
        User.objects.create_user('member', '', 'p', department=self.dept)
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('user:department_list'),
                                {'action': 'hard_delete', 'dept_id': self.dept.pk})
        self.assertContains(resp, '仍有成员')
        self.assertTrue(Department.objects.filter(pk=self.dept.pk).exists())

    def test_hard_delete_starts_counter_signature(self):
        """硬删：无成员时发起 dept_delete_requested（approval 插件建会签单）。"""
        from plugins.approval.models import Approval
        self.client.force_login(self.admin)
        self.client.post(reverse('user:department_list'),
                         {'action': 'hard_delete', 'dept_id': self.dept.pk})
        a = Approval.objects.filter(approval_type='dept_delete', biz_id=self.dept.pk).first()
        self.assertIsNotNone(a)
        self.assertEqual(a.status, Approval.Status.PENDING)
        self.assertTrue(Department.objects.filter(pk=self.dept.pk).exists())  # 未物理删除


class UserStatusV12Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin', '', 'adminpass')
        cls.manager = User.objects.create_user('mgr', '', 'mgrpass')
        cls.role = Role.objects.create(name='MGR')
        cls.role.permissions.add(P.get(codename='user_manage'))
        cls.manager.roles.add(cls.role)
        cls.target = User.objects.create_user('target', '', 'targetpass')

    def test_admin_disable_direct(self):
        """超管直接禁用：is_active=False + 上链信号。"""
        got = []
        bus.user_disabled.connect(lambda sender, **kw: got.append(kw), weak=False)
        self.client.force_login(self.admin)
        self.client.post(reverse('user:user_status', args=[self.target.pk]),
                         {'status': 'disable'})
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(self.target.permission_frozen)
        self.assertEqual(got[-1]['user_id'], self.target.pk)

    def test_manager_disable_requires_counter_signature(self):
        """普通管理员禁用：先冻结权限 + 发起 user_disable 会签单，不直接禁用。"""
        from plugins.approval.models import Approval
        self.client.force_login(self.manager)
        self.client.post(reverse('user:user_status', args=[self.target.pk]),
                         {'status': 'disable'})
        self.target.refresh_from_db()
        self.assertTrue(self.target.permission_frozen)      # 冻结即时
        self.assertTrue(self.target.is_active)              # 未直接禁用
        a = Approval.objects.filter(approval_type='user_disable', biz_id=self.target.pk).first()
        self.assertIsNotNone(a)
        self.assertEqual(a.status, Approval.Status.PENDING)

    def test_freeze_shortcuts_perm(self):
        """冻结权限：has_perm 即时短路为 False（超管除外）。"""
        self.target.permission_frozen = True
        self.target.save()
        self.assertFalse(self.target.has_perm('user_manage'))

    def test_guard_superuser(self):
        """权限层级：普通管理员不能操作超管。"""
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('user:user_status', args=[self.admin.pk]),
                                {'status': 'disable'})
        self.assertEqual(resp.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_password_confirm_mismatch(self):
        """密码二次确认：不一致校验失败。"""
        form = UserForm(data={
            'username': 'u1', 'password': 'abc12345', 'password_confirm': 'different'})
        self.assertFalse(form.is_valid())


class DeptHardDeleteCallbackTests(TestCase):
    """会签通过回调（user 订阅 counter_signature_approved）→ 物理删除。"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin', '', 'adminpass')
        cls.dept = Department.objects.create(name='临时部门')

    def test_counter_approved_deletes_dept(self):
        """dept_delete 会签全部通过 → 部门物理删除 + dept_deleted 上链。"""
        from plugins.approval.models import Approval
        from plugins.approval.services import start_counter_signature, sign_approve
        operator = self.admin
        approval = Approval.objects.create(
            approval_type=Approval.Type.DEPT_DELETE, title='删部门',
            content='物理删除', applicant=operator, approver=operator, biz_id=self.dept.pk)
        start_counter_signature(approval, [operator], operator)
        sign_approve(approval, operator, '同意')
        self.assertFalse(Department.objects.filter(pk=self.dept.pk).exists())
