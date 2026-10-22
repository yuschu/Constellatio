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


class UserPermissionScopeTests(TestCase):
    """编辑用户时只展示操作者可授予的权限。"""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user('mgr', '', 'pw')
        cls.manager.user_permissions.add(Permission.objects.get(codename='user_manage'))
        cls.admin = User.objects.create_superuser('root', '', 'pw')

    def test_manager_only_sees_own_permissions(self):
        form = UserForm(operator=self.manager)
        qs = form.fields['user_permissions'].queryset
        self.assertIn(Permission.objects.get(codename='user_manage'), qs)
        self.assertNotIn(Permission.objects.get(codename='dept_delete_approve'), qs)

    def test_superuser_sees_all_permissions(self):
        form = UserForm(operator=self.admin)
        self.assertEqual(form.fields['user_permissions'].queryset.count(),
                         Permission.objects.count())


class PermissionLevelTests(TestCase):
    """v1.5.4：权限等级标注、角色等级、个人中心全员基线展示。"""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user('mgr', '', 'pw')
        cls.manager.user_permissions.add(P.get(codename='user_manage'))
        cls.role = Role.objects.create(name='人力资源经理')
        cls.role.permissions.add(P.get(codename='attendance_report_view'))
        cls.manager.roles.add(cls.role)

    def test_form_label_carries_level(self):
        form = UserForm(operator=self.manager)
        label = form.fields['user_permissions'].label_from_instance(
            P.get(codename='attendance_report_view'))
        self.assertIn('L2 管理岗', label)
        self.assertIn('查看签到详情', label)

    def test_form_label_english(self):
        from django.utils import translation
        with translation.override('en'):
            form = UserForm(operator=self.manager)
            label = form.fields['user_permissions'].label_from_instance(
                P.get(codename='attendance_report_view'))
        self.assertIn('[L2 Manager]', label)
        self.assertIn('attendance', label)

    def test_role_level_and_empty_role(self):
        self.assertEqual(self.role.level, 20)
        self.assertEqual(self.role.level_label, 'L2 管理岗')
        empty = Role.objects.create(name='空权限角色')
        self.assertEqual(empty.level_label, 'L3 员工')

    def test_role_list_shows_level(self):
        admin = User.objects.create_superuser('root2', '', 'pw')
        self.client.force_login(admin)
        response = self.client.get(reverse('user:role_list'))
        self.assertContains(response, '权限等级')
        self.assertContains(response, 'L2 管理岗')

    def test_profile_shows_level_and_baseline(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('user:profile_permissions'))
        self.assertContains(response, 'L1 系统管理')
        self.assertContains(response, '全员基线权限')
        self.assertContains(response, '考勤打卡')


class PasswordPermissionTests(TestCase):
    """v1.5.5：仅超级管理员与账号本人可修改密码。"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('root', '', 'pw')
        cls.manager = User.objects.create_user('mgr', '', 'mgrpass')
        cls.manager.user_permissions.add(P.get(codename='user_manage'))
        cls.target = User.objects.create_user('target', '', 'oldpass123')

    def _data(self, **extra):
        data = {
            'username': 'target', 'last_name': '目标', 'email': '',
            'department': '', 'leader': '', 'roles': [], 'user_permissions': [],
            'is_active': 'on',
        }
        data.update(extra)
        return data

    def test_manager_cannot_change_other_password(self):
        form = UserForm(data=self._data(password='newpass123',
                                       password_confirm='newpass123'),
                        instance=self.target, operator=self.manager)
        self.assertNotIn('password', form.fields)
        self.assertTrue(form.is_valid())
        form.save()
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('oldpass123'))
        self.assertFalse(self.target.check_password('newpass123'))

    def test_superuser_can_change_other_password(self):
        form = UserForm(data=self._data(password='newpass123',
                                       password_confirm='newpass123'),
                        instance=self.target, operator=self.admin)
        self.assertIn('password', form.fields)
        self.assertTrue(form.is_valid())
        form.save()
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('newpass123'))

    def test_self_can_change_password(self):
        form = UserForm(data=self._data(password='selfpass123',
                                       password_confirm='selfpass123'),
                        instance=self.target, operator=self.target)
        self.assertIn('password', form.fields)
        self.assertTrue(form.is_valid())
        form.save()
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('selfpass123'))

    def test_manager_create_uses_default_password(self):
        form = UserForm(data={
            'username': 'fresh', 'last_name': '新人', 'email': '',
            'department': '', 'leader': '', 'roles': [], 'user_permissions': [],
            'is_active': 'on', 'password': 'hacker123', 'password_confirm': 'hacker123',
        }, operator=self.manager)
        self.assertNotIn('password', form.fields)
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.username, 'fresh')
        self.assertTrue(user.check_password('constellatio123'))
        self.assertFalse(user.check_password('hacker123'))


class ProfileTests(TestCase):
    """个人中心：资料编辑 / 权限查看 / 修改密码 / 顶栏入口。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'me', '', 'oldpass123', last_name='旧名')
        role = Role.objects.create(name='员工')
        role.permissions.add(Permission.objects.get(codename='user_manage'))
        cls.user.roles.add(role)
        cls.perm = Permission.objects.get(codename='user_manage')

    def setUp(self):
        self.client.force_login(self.user)

    def test_profile_and_topbar_link(self):
        response = self.client.get(reverse('user:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '个人中心')
        self.assertContains(response, '编辑资料')
        home = self.client.get('/')
        self.assertContains(home, '/plugins/user/profile/')

    def test_profile_permissions_page(self):
        response = self.client.get(reverse('user:profile_permissions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '员工')
        self.assertContains(response, self.perm.name)

    def test_profile_edit(self):
        response = self.client.post(reverse('user:profile_edit'), {
            'last_name': '新名', 'email': 'new@example.com'})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, '新名')
        self.assertEqual(self.user.email, 'new@example.com')

    def test_password_change(self):
        response = self.client.post(reverse('user:profile_password'), {
            'old_password': 'oldpass123',
            'new_password': 'newpass123',
            'confirm_password': 'newpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass123'))
        self.assertEqual(self.client.get(reverse('user:profile')).status_code, 200)

    def test_password_wrong_old(self):
        response = self.client.post(reverse('user:profile_password'), {
            'old_password': 'bad',
            'new_password': 'newpass123',
            'confirm_password': 'newpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '当前密码错误')
