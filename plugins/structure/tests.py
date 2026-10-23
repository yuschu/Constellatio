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

    def test_template_page_renders_user_template_groups(self):
        """v1.5.9：模板架构独立页面渲染模板部门/角色/用户（原总览的模板区块）。"""
        self._apply()
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('structure:template'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '钱招聘')
        self.assertContains(resp, '招聘组')
        self.assertContains(resp, 'IT运维工程师')
        self.assertContains(resp, '返回组织架构')

    def test_overview_shows_current_architecture(self):
        """v1.5.9：组织架构页展示真实部门/角色，并给出「查看模板」入口。"""
        from plugins.user.models import Department
        dept = Department.objects.create(name='当前研发部')
        Role.objects.create(name='当前工程师')
        self.admin.department = dept
        self.admin.save(update_fields=['department'])
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('structure:overview'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '当前部门树')
        self.assertContains(resp, '当前研发部')
        self.assertContains(resp, '当前角色')
        self.assertContains(resp, '当前工程师')
        self.assertContains(resp, '查看模板')

    def test_single_structure_menu(self):
        """v1.5.9：组织架构与应用结构合并为单一菜单入口。"""
        from plugin_host.registry import PLUGIN_REGISTRY
        menus = PLUGIN_REGISTRY['structure'].menus
        self.assertEqual(len(menus), 1)
        self.assertEqual(str(menus[0]['label']), '组织架构')
        self.assertEqual(menus[0]['url'], '/plugins/structure/')

    def test_template_page_apply_form_only_with_manage(self):
        """模板页：structure_view 可看，应用表单只对 structure_manage 渲染。"""
        viewer = User.objects.create_user('tpl_viewer', password='pw')
        role = Role.objects.create(name='模板查看')
        role.permissions.add(Permission.objects.get(codename='structure_view'))
        viewer.roles.add(role)
        self.client.force_login(viewer)
        resp = self.client.get(reverse('structure:template'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '⤓ 应用模板')

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('structure:template'))
        self.assertContains(resp, '⤓ 应用模板')

    def test_template_page_requires_structure_view(self):
        noperm = User.objects.create_user('tpl_noperm', password='pw')
        self.client.force_login(noperm)
        self.assertEqual(self.client.get(reverse('structure:template')).status_code, 302)


class UserHierarchyTests(TestCase):
    """v1.5.6：组织关系树（真实账号 + leader），责任划分口径。"""

    @classmethod
    def setUpTestData(cls):
        cls.gm = User.objects.create_user('tree_gm', last_name='张总', password='pw')
        cls.mgr = User.objects.create_user('tree_mgr', last_name='王经理', password='pw',
                                           leader=cls.gm)
        cls.staff_a = User.objects.create_user('tree_a', last_name='钱招聘', password='pw',
                                               leader=cls.mgr)
        cls.staff_b = User.objects.create_user('tree_b', last_name='孙培训', password='pw',
                                               leader=cls.mgr)
        cls.solo = User.objects.create_user('tree_solo', last_name='独立账号', password='pw')

    def test_tree_levels_and_counts(self):
        """层级与计数：根/子/孙、depth、直接下属、含下级合计。"""
        from .hierarchy import build_user_tree
        tree = build_user_tree()
        root_ids = {n['id'] for n in tree['roots']}
        self.assertEqual(root_ids, {self.gm.pk, self.solo.pk})
        mgr = next(n for n in tree['roots'][0]['children'] if n['id'] == self.mgr.pk)
        self.assertEqual(mgr['depth'], 1)
        self.assertEqual(mgr['direct_count'], 2)
        self.assertEqual(mgr['total_count'], 2)
        self.assertEqual({c['id'] for c in mgr['children']},
                         {self.staff_a.pk, self.staff_b.pk})
        self.assertEqual({c['depth'] for c in mgr['children']}, {2})
        self.assertEqual(tree['stats'], {
            'total': 5, 'with_leader': 3, 'roots': 2, 'cycles': 0, 'inactive': 0,
        })
        self.assertEqual(len(tree['rows']), 5)
        self.assertEqual(tree['rows'][0]['id'], self.gm.pk)
        self.assertEqual(tree['rows'][0]['direct_count'], 1)
        self.assertEqual(tree['rows'][0]['total_count'], 3)
        self.assertEqual(len({row['id'] for row in tree['rows']}), 5)

    def test_cycle_is_broken_and_marked(self):
        """A→B→A 与自环：提为根并标 is_cycle，不递归死循环、行不重复。"""
        from .hierarchy import build_user_tree
        a = User.objects.create_user('cycle_a', password='pw')
        b = User.objects.create_user('cycle_b', password='pw', leader=a)
        a.leader = b
        a.save(update_fields=['leader'])
        c = User.objects.create_user('cycle_c', password='pw', leader=a)
        d = User.objects.create_user('self_d', password='pw')
        d.leader = d
        d.save(update_fields=['leader'])

        tree = build_user_tree()
        roots = {n['id']: n for n in tree['roots']}
        self.assertTrue(roots[a.pk]['is_cycle'])
        self.assertTrue(roots[b.pk]['is_cycle'])
        self.assertTrue(roots[d.pk]['is_cycle'])
        # 环外账号仍挂在环上节点下，不丢节点
        self.assertEqual({ch['id'] for ch in roots[a.pk]['children']}, {c.pk})
        ids = [row['id'] for row in tree['rows']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids) & {a.pk, b.pk, c.pk, d.pk}, {a.pk, b.pk, c.pk, d.pk})
        self.assertEqual(tree['stats']['cycles'], 3)

    def test_inactive_account_kept_and_marked(self):
        """停用账号保留在树中（责任链不拆），stats.inactive 计数。"""
        from .hierarchy import build_user_tree
        self.gm.is_active = False
        self.gm.save(update_fields=['is_active'])
        tree = build_user_tree()
        gm_node = next(n for n in tree['roots'] if n['id'] == self.gm.pk)
        self.assertFalse(gm_node['is_active'])
        self.assertEqual([c['id'] for c in gm_node['children']], [self.mgr.pk])
        self.assertEqual(tree['stats']['inactive'], 1)
        row = next(r for r in tree['rows'] if r['id'] == self.gm.pk)
        self.assertFalse(row['is_active'])

    def test_department_tree(self):
        """v1.5.9：真实部门树——层级、成员数、停用标记与统计。"""
        from plugins.user.models import Department
        from .hierarchy import build_department_tree
        root = Department.objects.create(name='总公司')
        branch = Department.objects.create(name='研发中心', parent=root)
        frozen = Department.objects.create(name='停用组', parent=root, is_active=False)
        User.objects.create_user('dept_a', password='pw', department=branch)
        User.objects.create_user('dept_b', password='pw', department=branch)

        data = build_department_tree()
        self.assertEqual(data['stats'], {'total': 3, 'active': 2, 'members': 2})
        root_node = next(n for n in data['roots'] if n['id'] == root.pk)
        children = {n['name']: n for n in root_node['children']}
        self.assertEqual(children['研发中心']['member_count'], 2)
        self.assertFalse(children['停用组']['is_active'])
        self.assertEqual({n['id'] for n in data['roots']}, {root.pk})


class StructureOverviewTreeTests(TestCase):
    """v1.5.6：总览页关系树渲染与准入。"""

    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('tree_viewer', last_name='查看者', password='pw')
        role = Role.objects.create(name='关系树查看')
        role.permissions.add(Permission.objects.get(codename='structure_view'))
        cls.viewer.roles.add(role)
        cls.boss = User.objects.create_user('tree_boss', last_name='老板', password='pw')
        cls.worker = User.objects.create_user('tree_worker', last_name='员工甲', password='pw',
                                              leader=cls.boss)

    def test_overview_shows_tree_and_responsibility(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse('structure:overview'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '用户关系树（责任划分）')
        self.assertContains(resp, '责任人清单')
        self.assertContains(resp, '老板')
        self.assertContains(resp, '员工甲')
        self.assertContains(resp, '直属上级')
        self.assertEqual(resp.context['org_stats']['total'], 3)
        self.assertEqual(resp.context['org_stats']['roots'], 2)

    def test_tree_requires_structure_view(self):
        noperm = User.objects.create_user('tree_noperm', password='pw')
        self.client.force_login(noperm)
        self.assertEqual(
            self.client.get(reverse('structure:overview')).status_code, 302)

