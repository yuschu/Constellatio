"""structure 插件测试：模板完整性、幂等应用、归属、权限守卫、经理授权开关。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from . import template
from .services import apply_structure

from plugins.user.models import Role

User = get_user_model()


class StructureTemplateTests(TestCase):
    def test_template_integrity(self):
        """模板完整性：部门/角色/用户数量与名称口径。"""
        self.assertEqual(len(template.DEPARTMENTS), 20)
        self.assertEqual(len(template.ROLES), 31)
        self.assertEqual(len(template.USERS), 31)
        names = {d[0] for d in template.DEPARTMENTS}
        self.assertIn('总裁办', names)
        self.assertIn('运维组', names)
        self.assertEqual({u[3] for u in template.USERS}, set(template.ROLES))


class StructureApplyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin', '', 'adminpass')

    def _apply(self, grant=False):
        return apply_structure(self.admin, grant_manager_perms=grant)

    def test_apply_creates_all(self):
        """首次应用：全部创建且归属正确。"""
        d, r, u = self._apply()
        self.assertEqual(d, 20)
        self.assertEqual(r, 31)
        self.assertEqual(u, 31)
        user = User.objects.get(username='gm_zhang')
        self.assertEqual(user.last_name, '张总')
        self.assertEqual(user.department.name, '总裁办')
        self.assertTrue(user.roles.filter(name='总经理').exists())
        self.assertTrue(user.check_password('constellatio123'))

    def test_apply_idempotent(self):
        """幂等：二次应用全部计数为 0，不重复创建。"""
        self._apply()
        d, r, u = self._apply()
        self.assertEqual((d, r, u), (0, 0, 0))
        self.assertEqual(User.objects.filter(username='gm_zhang').count(), 1)

    def test_grant_manager_perms(self):
        """经理授权开关：开启后经理角色挂 user_manage，专员不挂。"""
        self._apply(grant=True)
        mgr = Permission.objects.get(codename='user_manage')
        self.assertTrue(
            User.objects.get(username='hr_wang').roles.filter(
                permissions__pk=mgr.pk).exists())
        self.assertFalse(
            User.objects.get(username='hr_qian').roles.filter(
                permissions__pk=mgr.pk).exists())

    def test_role_permission_template(self):
        """v1.5.4：应用模板即按角色授予权限（管理岗含签到详情，员工不含）。"""
        self._apply(grant=False)
        self.assertTrue(User.objects.get(username='hr_wang').has_perm('attendance_report_view'))
        self.assertTrue(User.objects.get(username='gm_zhang').has_perm('user_manage'))
        self.assertTrue(User.objects.get(username='it_zhou').has_perm('workspace_manage'))
        self.assertTrue(User.objects.get(username='hr_qian').has_perm('approval_view'))
        self.assertFalse(User.objects.get(username='hr_qian').has_perm('attendance_report_view'))

    def test_role_permission_template_is_idempotent_additive(self):
        """权限模板幂等：重复应用不抹掉人工追加的权限。"""
        from plugins.user.models import Role
        self._apply(grant=False)
        role = Role.objects.get(name='招聘专员')
        extra = Permission.objects.get(codename='notice_manage')
        role.permissions.add(extra)
        self._apply(grant=False)
        self.assertTrue(role.permissions.filter(pk=extra.pk).exists())
        self.assertTrue(role.permissions.filter(codename='approval_view').exists())

    def test_overview_requires_structure_view(self):
        """总览准入：无 structure_view 302；有则 200。"""
        noperm = User.objects.create_user('noperm2', '', 'pw')
        self.client.force_login(noperm)
        self.assertEqual(self.client.get(reverse('structure:overview')).status_code, 302)
        _role = Role.objects.create(name='架构查看')
        _role.permissions.add(Permission.objects.get(codename='structure_view'))
        noperm.roles.add(_role)
        self.assertEqual(self.client.get(reverse('structure:overview')).status_code, 200)

    def test_grant_role_perms_command(self):
        """管理命令：为既有角色幂等补齐模板权限（升级老库用）。"""
        import io
        from django.core.management import call_command
        Role.objects.create(name='人力资源经理')
        call_command('grant_role_perms', stdout=io.StringIO())
        role = Role.objects.get(name='人力资源经理')
        self.assertTrue(role.permissions.filter(codename='attendance_report_view').exists())
        self.assertTrue(role.permissions.filter(codename='approval_approve').exists())
        # 幂等：再跑一次不报错、不重复
        call_command('grant_role_perms', stdout=io.StringIO())
        self.assertEqual(role.permissions.filter(codename='attendance_report_view').count(), 1)

    def test_grant_role_perms_revoke_manager_user_manage(self):
        """升级选项：收回部门经理 L1 user_manage，保留总经理/系统管理员。"""
        import io
        from django.core.management import call_command
        user_manage = Permission.objects.get(codename='user_manage')
        manager_role = Role.objects.create(name='人力资源经理')
        manager_role.permissions.add(user_manage)
        gm_role = Role.objects.create(name='总经理')
        gm_role.permissions.add(user_manage)
        call_command('grant_role_perms', '--revoke-manager-perms',
                     stdout=io.StringIO())
        self.assertFalse(manager_role.permissions.filter(codename='user_manage').exists())
        self.assertTrue(gm_role.permissions.filter(codename='user_manage').exists())
        self.assertTrue(
            manager_role.permissions.filter(codename='attendance_report_view').exists())

    def test_apply_seeds_leaders(self):
        """v1.5.5：应用模板补齐直属上级（组员→部门负责人→总经理）。"""
        self._apply()
        self.assertEqual(User.objects.get(username='hr_qian').leader.username, 'hr_wang')
        self.assertEqual(User.objects.get(username='hr_wang').leader.username, 'gm_zhang')
        self.assertIsNone(User.objects.get(username='gm_zhang').leader)
        # 幂等：人工调整不覆盖
        hr_qian = User.objects.get(username='hr_qian')
        hr_qian.leader = User.objects.get(username='gm_zhang')
        hr_qian.save(update_fields=['leader'])
        self._apply()
        hr_qian.refresh_from_db()
        self.assertEqual(hr_qian.leader.username, 'gm_zhang')

    def test_apply_requires_perm(self):
        """权限守卫：无 structure_manage 的 apply 请求被拒。"""
        self.client.force_login(self.admin)
        noperm = User.objects.create_user('noperm', '', 'nopermpass')
        self.client.force_login(noperm)
        resp = self.client.post(reverse('structure:apply'))
        self.assertEqual(resp.status_code, 302)

    def test_apply_emits_signal(self):
        """应用后发 structure_applied 信号并落 StructureRecord。"""
        from plugin_host.signals import structure_applied
        got = []
        structure_applied.connect(lambda sender, **kw: got.append(kw), weak=False)
        self._apply()
        self.assertEqual(got[-1]['dept_created'], 20)
        from .models import StructureRecord
        self.assertEqual(StructureRecord.objects.count(), 1)
