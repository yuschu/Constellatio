"""v1.7.14：approval 附件 service 层单测（校验 / 落盘 / 鉴权），零 request。

覆盖 review 要求的边界：附件超限、无权限下载、无附件回详情。
"""

import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from plugin_host.exceptions import ObjectPermissionDenied

from . import services
from .models import Approval

User = get_user_model()


class AttachmentServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.media = tempfile.mkdtemp()
        cls.applicant = User.objects.create_user('att_app', password='pw')
        cls.approver = User.objects.create_user('att_approver', password='pw')
        cls.outsider = User.objects.create_user('att_other', password='pw')
        cls.admin = User.objects.create_superuser('att_admin', '', 'pw')
        cls.approval = Approval.objects.create(
            applicant=cls.applicant, approver=cls.approver,
            approval_type='seal', status=Approval.Status.PENDING,
            form_data={'purpose': '合同用章'})

    def setUp(self):
        patcher = override_settings(MEDIA_ROOT=self.media)
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def _upload(self, name='contract.pdf', size=16):
        return SimpleUploadedFile(name, b'%PDF-1.4' + b'0' * size, content_type='application/pdf')

    def test_validate_accepts_allowed_extension(self):
        upload = self._upload()
        self.assertIs(services.validate_attachment(upload), upload)

    def test_validate_rejects_unknown_extension(self):
        with self.assertRaises(services.AttachmentError):
            services.validate_attachment(self._upload(name='payload.exe'))

    def test_validate_rejects_oversize(self):
        """超限判据用 mock 把大小放大到上限之上，不真的造 10MB 文件。"""
        upload = self._upload(name='big.pdf')
        with mock.patch.object(type(upload), 'size', property(lambda self: 10 * 1024 * 1024 + 1)):
            with self.assertRaises(services.AttachmentError):
                services.validate_attachment(upload)

    def test_store_attachment_persists_file(self):
        stored = services.store_attachment(self.approval, self._upload())
        self.assertTrue(stored.name.endswith('.pdf'))
        self.approval.refresh_from_db()
        self.assertTrue(self.approval.attachment.name.endswith('.pdf'))

    def test_store_attachment_rejects_invalid_and_keeps_empty(self):
        with self.assertRaises(services.AttachmentError):
            services.store_attachment(self.approval, self._upload(name='x.exe'))
        self.approval.refresh_from_db()
        self.assertFalse(self.approval.attachment)

    def test_may_view_matrix(self):
        self.assertTrue(services.may_view(self.applicant, self.approval))
        self.assertTrue(services.may_view(self.approver, self.approval))
        self.assertTrue(services.may_view(self.admin, self.approval))
        self.assertFalse(services.may_view(self.outsider, self.approval))

    def test_attachment_for_rejects_outsider(self):
        services.store_attachment(self.approval, self._upload())
        with self.assertRaises(ObjectPermissionDenied):
            services.attachment_for(self.outsider, self.approval)

    def test_attachment_for_returns_none_without_file(self):
        """相关人但单据没有附件：返回 None（视图据此回详情，而不是 404/403）。"""
        self.assertIsNone(services.attachment_for(self.applicant, self.approval))

    def test_attachment_for_returns_handle_for_involved_user(self):
        services.store_attachment(self.approval, self._upload())
        handle = services.attachment_for(self.applicant, self.approval)
        self.assertTrue(handle.read().startswith(b'%PDF-1.4'))
        handle.close()
