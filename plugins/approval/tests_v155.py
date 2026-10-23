"""v1.5.5 审批测试：动态表单 / 审批人留空 / 抄送上级 / 调休关联加班。

v1.5.14：报销金额必填、用章文件上传与下载权限。
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
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
        grant(cls.leader, 'approval_view', 'approval_approve', name='经理审批')
        grant(cls.gm, 'approval_view', 'approval_approve', name='总经理审批')

    def setUp(self):
        self.client.force_login(self.applicant)

    def test_type_tabs_render_dynamic_fields(self):
        cases = {
            'leave': ('请假时间', '事由'),
            'expense': ('提交时间', '金额', '费用事由'),
            'seal': ('申请用章时间', '用章文件', '用途'),
            'outing': ('外出开始时间', '外出结束时间', '外出事由'),
            'overtime': ('加班开始时间', '加班结束时间', '加班事由'),
            'comp': ('调休开始时间', '调休结束时间', '调休依据'),
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
            'approver': str(self.gm.pk),
        })
        self.assertEqual(response.status_code, 302)
        approval = Approval.objects.get(applicant=self.applicant)
        self.assertEqual(approval.approver, self.gm)
        self.assertEqual(approval.department_name, '研发部')
        self.assertEqual(approval.status, Approval.Status.PENDING)
        self.assertEqual(approval.form_data['reason'], '家事')
        self.assertIn(self.leader, approval.cc_users.all())   # v1.5.18：抄送申请人直系领导

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
        self.assertIn(self.leader, approval.cc_users.all())   # 抄送申请人直系领导

    def test_end_time_must_be_later(self):
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'overtime',
            'start_time': '2026-11-03T12:00',
            'end_time': '2026-11-03T09:00',
            'reason': '赶版本',
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Approval.objects.exists())

    def test_comp_requires_overtime_record(self):
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'comp',
            'start_time': '2026-11-05T09:00',
            'end_time': '2026-11-05T18:00',
            'basis': '',
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
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
            'start_time': '2026-11-05T09:00',
            'end_time': '2026-11-05T18:00',
            'basis': str(overtime.pk),
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
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
            'approver': str(self.gm.pk),
        })
        approval = Approval.objects.get(applicant=self.applicant)
        self.assertEqual(approval.status, Approval.Status.PENDING)

        self.client.force_login(self.gm)   # 审批人本人
        response = self.client.post(
            reverse('approval:approval_detail', args=[approval.pk]),
            {'action': 'approve', 'comment': '同意'})
        self.assertEqual(response.status_code, 302)
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)
        self.assertIn(self.leader, approval.cc_users.all())  # 完成后仍抄送申请人直系领导

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

    def test_expense_amount_required_and_saved(self):
        """v1.5.14：报销金额必填，保存到 amount 与 form_data。"""
        url = reverse('approval:approval_create')
        base = {
            'approval_type': 'expense', 'submit_time': '2026-11-04',
            'reason': '差旅报销', 'department': str(self.dept.pk), 'approver': str(self.gm.pk),
        }
        response = self.client.post(url, base)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Approval.objects.filter(
            applicant=self.applicant, approval_type='expense').exists())

        response = self.client.post(url, dict(base, amount='288.50'))
        self.assertEqual(response.status_code, 302)
        approval = Approval.objects.get(applicant=self.applicant, approval_type='expense')
        self.assertEqual(str(approval.amount), '288.50')
        self.assertEqual(approval.form_data['amount'], '288.50')
        detail = self.client.get(reverse('approval:approval_detail', args=[approval.pk]))
        self.assertContains(detail, '￥288.50')

    def test_seal_attachment_required_saved_and_downloadable(self):
        """v1.5.14：用章文件必填、落盘、详情下载；无关人员不可下载。"""
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        url = reverse('approval:approval_create')
        base = {
            'approval_type': 'seal', 'seal_time': '2026-11-05T09:00',
            'purpose': '合同用章', 'department': str(self.dept.pk), 'approver': str(self.gm.pk),
        }
        with override_settings(MEDIA_ROOT=media):
            response = self.client.post(url, base)
            self.assertEqual(response.status_code, 200)      # 缺附件 → 表单报错
            self.assertFalse(Approval.objects.filter(approval_type='seal').exists())

            upload = SimpleUploadedFile(
                'contract.pdf', b'%PDF-1.4 demo', content_type='application/pdf')
            response = self.client.post(url, dict(base, seal_file=upload))
            self.assertEqual(response.status_code, 302)
            approval = Approval.objects.get(approval_type='seal')
            self.assertTrue(approval.attachment.name.endswith('.pdf'))
            self.assertEqual(approval.form_data['seal_file'], 'contract.pdf')
            self.assertEqual(approval.form_data['purpose'], '合同用章')

            detail = self.client.get(reverse('approval:approval_detail', args=[approval.pk]))
            self.assertContains(detail, '下载附件')

            download = self.client.get(
                reverse('approval:approval_attachment', args=[approval.pk]))
            self.assertEqual(download.status_code, 200)
            self.assertIn('attachment', download['Content-Disposition'])

            outsider = User.objects.create_user('seal_outsider', password='pw')
            self.client.force_login(outsider)
            blocked = self.client.get(
                reverse('approval:approval_attachment', args=[approval.pk]))
            self.assertEqual(blocked.status_code, 302)

    def test_seal_rejects_unsupported_extension(self):
        """v1.5.14：用章附件仅允许常见文档 / 图片扩展名。"""
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media):
            upload = SimpleUploadedFile(
                'payload.exe', b'MZ', content_type='application/octet-stream')
            response = self.client.post(reverse('approval:approval_create'), {
                'approval_type': 'seal', 'seal_time': '2026-11-05T09:00',
                'seal_file': upload, 'department': str(self.dept.pk), 'approver': str(self.gm.pk),
            })
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Approval.objects.filter(approval_type='seal').exists())

    def test_cc_list_visible_to_superior(self):
        self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'leave',
            'leave_time': '2026-11-02T09:00',
            'reason': '家事',
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
        })
        approval = Approval.objects.get(applicant=self.applicant)
        self.client.force_login(self.leader)
        response = self.client.get(reverse('approval:approval_cc'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, approval.title)

    def test_comp_end_must_be_after_start(self):
        """v1.5.15：调休为时间段，结束必须晚于开始。"""
        overtime = Approval.objects.create(
            approval_type=Approval.Type.OVERTIME, title='加班',
            applicant=self.applicant, approver=self.leader,
            form_data={'start_time': '2026-10-20T19:00',
                       'end_time': '2026-10-20T22:00'})
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'comp',
            'start_time': '2026-11-05T18:00',
            'end_time': '2026-11-05T09:00',
            'basis': str(overtime.pk),
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '结束时间必须晚于开始时间')
        self.assertFalse(Approval.objects.filter(approval_type='comp').exists())

    def test_l3_pending_list_hidden_manager_visible(self):
        """v1.5.15：L3（仅 approval_view）看不到待我审批；管理岗可见。"""
        self.assertEqual(
            self.client.get(reverse('approval:approval_pending')).status_code, 302)
        self.assertNotContains(self.client.get('/'), '/plugins/approval/pending/')

        manager = User.objects.create_user('pending_mgr', password='pw')
        grant(manager, 'approval_view', 'approval_approve', name='待办管理岗')
        self.client.force_login(manager)
        self.assertEqual(
            self.client.get(reverse('approval:approval_pending')).status_code, 200)
        self.assertContains(self.client.get('/'), '/plugins/approval/pending/')

    def test_expense_routes_to_finance_manager(self):
        """v1.5.15：报销流转到财务部（财务经理），优先于手动指定。"""
        finance = Department.objects.create(name='财务部')
        role = Role.objects.create(name='财务经理')
        manager = User.objects.create_user(
            'fin_mgr', password='pw', last_name='财务经理', department=finance)
        manager.roles.add(role)
        response = self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'expense',
            'submit_time': '2026-11-06',
            'amount': '100.00',
            'reason': '差旅',
            'department': str(self.dept.pk),
            'approver': str(manager.pk),
        })
        self.assertEqual(response.status_code, 302)
        approval = Approval.objects.get(approval_type='expense')
        self.assertEqual(approval.approver, manager)

    def test_leave_routes_to_hr_manager(self):
        """v1.5.15：请假流转到人力资源部（人力资源经理）。"""
        hr = Department.objects.create(name='人力资源部')
        role = Role.objects.create(name='人力资源经理')
        manager = User.objects.create_user(
            'hr_mgr', password='pw', last_name='HR 经理', department=hr)
        manager.roles.add(role)
        self.client.post(reverse('approval:approval_create'), {
            'approval_type': 'leave',
            'leave_time': '2026-11-07T09:00',
            'reason': '家事',
            'department': str(self.dept.pk),
            'approver': str(manager.pk),
        })
        approval = Approval.objects.get(approval_type='leave')
        self.assertEqual(approval.approver, manager)

    def test_seal_approval_applies_placeholder_e_seal(self):
        """v1.5.15：用章通过后写入电子盖章占位文本与流转记录。"""
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media):
            self.client.post(reverse('approval:approval_create'), {
                'approval_type': 'seal',
                'seal_time': '2026-11-08T09:00',
                'purpose': '合同用章',
                'seal_file': SimpleUploadedFile(
                    'seal.pdf', b'%PDF-1.4 seal', content_type='application/pdf'),
                'department': str(self.dept.pk),
                'approver': str(self.leader.pk),
            })
        approval = Approval.objects.get(approval_type='seal')
        self.assertEqual(approval.approver, self.leader)   # 无行政部时回退直属上级

        self.client.force_login(self.leader)
        response = self.client.post(
            reverse('approval:approval_detail', args=[approval.pk]),
            {'action': 'approve', 'comment': '同意'})
        self.assertEqual(response.status_code, 302)
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)
        self.assertEqual(approval.form_data['e_seal']['status'], 'placeholder')
        self.assertTrue(approval.records.filter(action='e_seal').exists())

        detail = self.client.get(reverse('approval:approval_detail', args=[approval.pk]))
        self.assertContains(detail, '电子盖章')
        self.assertContains(detail, '待接入')

    def test_reapply_opens_prefilled_editable_form(self):
        """v1.5.17：重新申请进入可编辑表单并预填原单内容。"""
        rejected = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.REJECTED,
            form_data={'leave_time': '2026-11-01T09:00', 'reason': '家事'},
            department_id=self.dept.pk, department_name='研发部')
        self.client.force_login(self.applicant)
        response = self.client.get(
            reverse('approval:approval_create'), {'reapply': rejected.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '原申请')
        self.assertContains(response, '确认重新发起')
        self.assertContains(response, '家事')          # 事由预填
        self.assertContains(response, '2026-11-01T09:00')

    def test_reapply_submit_replaces_rejected_record(self):
        """v1.5.17：确认重新发起后生成新单并替换原驳回记录。"""
        rejected = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.REJECTED,
            form_data={'leave_time': '2026-11-01T09:00', 'reason': '家事'},
            department_id=self.dept.pk, department_name='研发部')
        self.client.force_login(self.applicant)
        response = self.client.post(reverse('approval:approval_create'), {
            'reapply_of': str(rejected.pk),
            'approval_type': 'leave',
            'leave_time': '2026-11-02T09:00',
            'reason': '修改后的家事',
            'department': str(self.dept.pk),
            'approver': str(self.gm.pk),
        })
        self.assertEqual(response.status_code, 302)
        rejected.refresh_from_db()
        new = rejected.replaced_by
        self.assertIsNotNone(new)
        self.assertEqual(new.status, Approval.Status.PENDING)
        self.assertEqual(new.form_data['reason'], '修改后的家事')
        self.assertTrue(rejected.applicant_hidden)
        self.assertTrue(rejected.records.filter(action='replaced').exists())

        listing = self.client.get(reverse('approval:approval_list'))
        self.assertNotContains(listing, f'<td>{rejected.pk}</td>')
        self.assertContains(listing, f'<td>{new.pk}</td>')

    def test_hide_rejected_only_affects_applicant_list(self):
        """v1.5.16：删除申请记录 = 对申请人隐藏，数据保留。"""
        rejected = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='已驳回单',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.REJECTED)
        pending = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='待审批单',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.PENDING)
        self.client.force_login(self.applicant)
        response = self.client.post(reverse('approval:approval_hide', args=[rejected.pk]))
        self.assertEqual(response.status_code, 302)
        rejected.refresh_from_db()
        self.assertTrue(rejected.applicant_hidden)
        listing = self.client.get(reverse('approval:approval_list'))
        self.assertNotContains(listing, '已驳回单')
        self.assertContains(listing, '待审批单')
        self.assertEqual(
            self.client.get(reverse('approval:approval_detail', args=[rejected.pk])).status_code,
            200)

    def test_reapply_hide_guard_owner_and_status(self):
        """v1.5.17：仅申请人、仅已驳回可重新申请 / 隐藏。"""
        pending = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='待审批单',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.PENDING)
        self.client.force_login(self.applicant)
        # 非驳回不能进入重新申请表单
        self.assertEqual(self.client.get(
            reverse('approval:approval_create'), {'reapply': pending.pk}).status_code, 302)
        self.client.post(reverse('approval:approval_hide', args=[pending.pk]))
        pending.refresh_from_db()
        self.assertFalse(pending.applicant_hidden)

        other = User.objects.create_user('other_app', password='pw')
        grant(other, 'approval_view', name='他人查看')
        self.client.force_login(other)
        self.assertEqual(self.client.post(
            reverse('approval:approval_hide', args=[pending.pk])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse('approval:approval_create'), {'reapply': pending.pk}).status_code, 302)

    def test_detail_hides_empty_items(self):
        """v1.5.17：详情隐藏空内容项（事由 / 金额 / 抄送）。"""
        approval = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='仅时间',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.PENDING,
            form_data={'leave_time': '2026-11-01T09:00'})
        self.client.force_login(self.applicant)
        response = self.client.get(
            reverse('approval:approval_detail', args=[approval.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<th>事由</th>')
        self.assertNotContains(response, '<th>金额</th>')
        self.assertNotContains(response, '暂无抄送人')
        self.assertContains(response, '请假时间')

    def test_cc_hidden_for_l3_visible_for_manager(self):
        """v1.5.17：抄送我的仅管理岗可见。"""
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(reverse('approval:approval_cc')).status_code, 302)
        manager = User.objects.create_user('cc_mgr', password='pw')
        grant(manager, 'approval_view', 'approval_approve', name='抄送管理岗')
        self.client.force_login(manager)
        self.assertEqual(self.client.get(reverse('approval:approval_cc')).status_code, 200)

    def test_final_approval_cannot_be_modified(self):
        """v1.5.17：审批通过后无操作入口，仅显示已处理。"""
        approval = Approval.objects.create(
            approval_type=Approval.Type.LEAVE, title='请假',
            applicant=self.applicant, approver=self.leader,
            status=Approval.Status.PENDING)
        self.client.force_login(self.leader)
        self.client.post(reverse('approval:approval_detail', args=[approval.pk]),
                         {'action': 'approve', 'comment': '同意'})
        approval.refresh_from_db()
        self.assertEqual(approval.status, Approval.Status.APPROVED)
        self.client.force_login(self.applicant)
        detail = self.client.get(reverse('approval:approval_detail', args=[approval.pk]))
        self.assertNotContains(detail, '审批操作')
        self.assertContains(detail, '该申请已处理，不可修改。')
