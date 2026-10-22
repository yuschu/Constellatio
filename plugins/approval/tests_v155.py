"""v1.5.5 审批测试：动态表单 / 审批人留空 / 抄送上级 / 调休关联加班。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from plugins.user.models import Department, Role

from .models import Approval

User = get_user_model()


def grant(user, *codes, name=None):
    role = Role.objects.create(name=name or f'role-{user.username}')
    for code in codes:
        role.permissions.add(Permission.objects.get(codename=code))
    user.roles.add(role)
    return role


class DynamicApprovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='研发部')
        cls.gm = User.objects.create_user('gm', '', 'pw', last_name='总经理')
        cls.leader = User.objects.create_user(
            'lead', '', 'pw', last_name='研发经理', leader=cls.gm)
        cls.applicant = User.objects.create_user(
            'app', '', 'pw', last_name='朱研发',
            department=cls.dept, leader=cls.leader)
        grant(cls.applicant, 'approval_view', name='员工审批')
        grant(cls.leader, 'approval_view', name='经理审批')
        grant(cls.gm, 'approval_view', name='总经理审批')

    def setUp(self):
        self.client.force_login(self.applicant)

    def test_type_tabs_render_dynamic_fields(self):
        cases = {
            'leave': ('请假时间', '事由'),
            'expense': ('提交时间', '费用事由'),
            'seal': ('申请用章时间', '用章文件及用途'),
            'outing': ('外出开始时间', '外出结束时间', '外出事由'),
            'overtime': ('加班开始时间', '加班结束时间', '加班事由'),
            'comp': ('调休时间', '调休依据'),
        }
        for key, labels in cases.items():
            with self.subTest(type=key):
                response = self.client.get(reverse('approval:approval_create'), {'type': key})
                self.assertEqual(response.status_code, 200)
                for label in labels:
                    self.assertContains(response, label)
                self.assertContains(response, '部门')
                self.assertContains(response, '审批人')
                self.assertContains(response, f'value="{key}"')

    def test_leave_submit_assigns_leader_and_cc_superior(self):
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'leave',
            'leave_time': '2026-11-02T09:00',
            'reason': '家事',
            'department': str(self.dept.pk),
            'approver': '',
        })
        self.assertEqual(response.status_code, 302)
        approval = Approval.objects.get(applicant=self.applicant)
        self.assertEqual(approval.approver, self.leader)      # 留空 → 直属上级
        self.assertEqual(approval.department_name, '研发部')
        self.assertEqual(approval.status, Approval.Status.PENDING)
        self.assertEqual(approval.form_data['reason'], '家事')
        self.assertIn(self.gm, approval.cc_users.all())      # 抄送审批人上级

    def test_explicit_approver(self):
        self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'outing',
            'start_time': '2026-11-03T09:00',
            'end_time': '2026-11-03T12:00',
            'reason': '拜访客户',
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
        })
        approval = Approval.objects.get(applicant=self.applicant)
        self.assertEqual(approval.approver, self.gm)
        self.assertFalse(approval.cc_users.exists())          # 审批人无上级则无抄送

    def test_end_time_must_be_later(self):
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'overtime',
            'start_time': '2026-11-03T12:00',
            'end_time': '2026-11-03T09:00',
            'reason': '赶版本',
            'department': str(self.dept.pk),
            'approver': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Approval.objects.exists())

    def test_comp_requires_overtime_record(self):
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'comp',
            'comp_time': '2026-11-05T09:00',
            'basis': '',
            'department': str(self.dept.pk),
            'approver': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Approval.objects.exists())

    def test_comp_with_overtime_choice(self):
        overtime = Approval.objects.create(
            approval_type=Approval.Type.OVERTIME, title='加班',
            applicant=self.applicant, approver=self.leader,
            form_data={'start_time': '2026-10-20T19:00',
                       'end_time': '2026-10-20T22:00'})
        response = self.client.get(reverse('approval:approval_create'), {'type': 'comp'})
        self.assertContains(response, f'#{overtime.pk}')
        self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'comp',
            'comp_time': '2026-11-05T09:00',
            'basis': str(overtime.pk),
            'department': str(self.dept.pk),
            'approver': '',
        })
        comp = Approval.objects.get(approval_type=Approval.Type.COMP)
        self.assertEqual(comp.form_data['basis'], str(overtime.pk))
        self.assertIn(f'#{overtime.pk}', comp.form_data['basis_label'])
        self.assertIn('调休依据', comp.content)

    def test_approve_result_and_cc_on_completion(self):
        self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'leave',
            'leave_time': '2026-11-02T09:00',
            'reason': '家事',
            'department': str(self.dept.pk),
            'approver': '',
        })
        approval = Approval.objects.get(applicant=self.applicant)
        self.assertEqual(approval.status, Approval.Status.PENDING)

        self.client.force_login(self.leader)
        response = self.client.post(
            reverse('approval:approval_detail', args=[approval.pk]),
            {'action': 'approve', 'comment': '同意'})
        self.assertEqual(response.status_code, 302)
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)
        self.assertIn(self.gm, approval.cc_users.all())      # 完成后仍抄送上级

        # 申请人可查看结果
        self.client.force_login(self.applicant)
        detail = self.client.get(reverse('approval:approval_detail', args=[approval.pk]))
        self.assertContains(detail, '已通过')
        self.assertContains(detail, '请假时间')
        self.assertContains(detail, '部门')

    def test_dynamic_form_english(self):
        self.client.cookies['django_language'] = 'en'
        response = self.client.get(reverse('approval:approval_create'), {'type': 'outing'})
        self.assertContains(response, 'Outing start')
        self.assertContains(response, 'Outing end')
        self.assertContains(response, 'Select approval type')
        self.assertContains(response, 'Outing')

    def test_cc_list_visible_to_superior(self):
        self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'leave',
            'leave_time': '2026-11-02T09:00',
            'reason': '家事',
            'department': str(self.dept.pk),
            'approver': '',
        })
        approval = Approval.objects.get(applicant=self.applicant)
        self.client.force_login(self.gm)
        response = self.client.get(reverse('approval:approval_cc'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, approval.title)
