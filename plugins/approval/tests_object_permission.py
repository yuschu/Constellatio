"""v1.7.10 对象级越权：审批详情 / 附件 / 隐藏 → 403。

与 v1.7.9 的功能级 403 配套：功能级管「有没有这个功能」，对象级管「这张单子是不是你的」。
本文件 7 条用例覆盖三种入口 + `services` 的 `PermissionError` 分支。
"""

import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import FileResponse
from django.test import TestCase, override_settings
from django.urls import reverse

from plugins.approval.models import Approval
from plugins.user.models import Department, Role

User = get_user_model()


def grant(user, *codes, name=None):
    role = Role.objects.create(name=name or f'role-{user.username}')
    for code in codes:
        role.permissions.add(Permission.objects.get(codename=code))
    user.roles.add(role)
    return role


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ObjectPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='对象级测试部')
        cls.gm = User.objects.create_user('obj_gm', '', 'pw', last_name='总经理')
        cls.leader = User.objects.create_user(
            'obj_lead', '', 'pw', last_name='部门经理', leader=cls.gm)
        cls.applicant = User.objects.create_user(
            'obj_app', '', 'pw', last_name='申请人',
            department=cls.dept, leader=cls.leader)
        cls.outsider = User.objects.create_user('obj_other', '', 'pw', last_name='无关员工')
        for user in (cls.applicant, cls.outsider):
            # 两人都有 approval_view（全员基线码）——功能级都通过，只剩对象级判定
            grant(user, 'approval_view')

        cls.approval = Approval.objects.create(
            applicant=cls.applicant, approver=cls.gm,
            approval_type='leave', status=Approval.Status.PENDING,
            form_data={'reason': '年假'},
        )

    def _detail_url(self):
        return reverse('approval:approval_detail', args=[self.approval.pk])

    def _attachment_url(self):
        return reverse('approval:approval_attachment', args=[self.approval.pk])

    # 1
    def test_outsider_detail_gets_403(self):
        """无关员工（仅有功能级权限）看别人单据 → 403 品牌页。"""
        self.client.force_login(self.outsider)
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, '403', status_code=403)
        # 页面固定文案，不回显异常 message
        self.assertNotContains(response, '该审批单不属于你', status_code=403)

    # 2
    def test_outsider_attachment_gets_403_without_bytes(self):
        """附件：403 且**不能有任何文件字节流出**（FileResponse 在 raise 之后）。"""
        self.approval.attachment = SimpleUploadedFile('seal.pdf', b'%PDF-1.4 secret')
        self.approval.save(update_fields=['attachment', 'updated_at'])

        self.client.force_login(self.outsider)
        response = self.client.get(self._attachment_url())
        self.assertEqual(response.status_code, 403)
        self.assertNotIsInstance(response, FileResponse)
        self.assertContains(response, '403', status_code=403)

    # 3
    def test_viewer_cannot_act_gets_403_and_state_unchanged(self):
        """可看不可批（抄送人）POST 通过 → 403，且单据状态不变。"""
        self.approval.cc_users.add(self.outsider)
        self.client.force_login(self.outsider)
        response = self.client.post(self._detail_url(), {'action': 'approve', 'comment': '同意'})
        self.assertEqual(response.status_code, 403)
        self.approval.refresh_from_db()
        self.assertEqual(self.approval.status, Approval.Status.PENDING)

    # 4
    def test_applicant_and_approver_still_200(self):
        """防误伤：申请人、审批人本人均 200。"""
        for user in (self.applicant, self.gm):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self._detail_url()).status_code, 200)

    # 5
    def test_json_403_carries_message(self):
        """`Accept: application/json` → 403 JSON，message 是对象级文案。"""
        self.client.force_login(self.outsider)
        response = self.client.get(self._detail_url(), HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload['code'], 'permission_denied')
        self.assertEqual(payload['message'], '该审批单不属于你')

    # 6
    def test_hide_by_non_applicant_gets_403_and_no_write(self):
        """非申请人隐藏别人的单子 → 403，并且 `applicant_hidden` 仍为 False（不只是状态码）。"""
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('approval:approval_hide', args=[self.approval.pk]))
        self.assertEqual(response.status_code, 403)
        self.approval.refresh_from_db()
        self.assertFalse(self.approval.applicant_hidden)

    # 7
    def test_service_permission_error_becomes_403(self):
        """`services` 抛的 PermissionError 不再被静默吞掉（v1.7.10 改 B 方案）。

        用 mock 让 services 层抛错：_can_act 已通过（审批人本人），异常在调用链里冒出。
        """
        self.client.force_login(self.gm)
        with patch('plugins.approval.views.approve', side_effect=PermissionError('您不是该单据的审批人')):
            response = self.client.post(
                self._detail_url(), {'action': 'approve', 'comment': '同意'})
        self.assertEqual(response.status_code, 403)
        self.approval.refresh_from_db()
        self.assertEqual(self.approval.status, Approval.Status.PENDING)
