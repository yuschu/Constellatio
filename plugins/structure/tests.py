"""structure 插件测试：模板完整性、幂等应用、归属、权限守卫、经理授权开关。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from . import template
from .services import apply_structure

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
