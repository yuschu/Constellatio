"""notice 单元测试：发布可见 / 已读统计 / 已读去重。"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Announcement, AnnouncementRead

User = get_user_model()


class NoticeTest(TestCase):
    def setUp(self):
        self.publisher = User.objects.create_user('publisher', password='pw')
        self.reader = User.objects.create_user('reader', password='pw')

    def _announcement(self, **kw):
        defaults = {'title': '公告', 'content': '正文'}
        defaults.update(kw)
        return Announcement.objects.create(publisher=self.publisher, **defaults)

    def test_list_orders_top_first(self):
        a1 = self._announcement(title='普通公告')
        a2 = self._announcement(title='置顶公告', is_top=True)
        ids = list(Announcement.objects.values_list('id', flat=True))
        self.assertEqual(ids, [a2.id, a1.id])

    def test_read_counts_and_idempotent(self):
        a = self._announcement()
        AnnouncementRead.objects.create(announcement=a, user=self.reader)
        AnnouncementRead.objects.get_or_create(announcement=a, user=self.reader)
        self.assertEqual(AnnouncementRead.objects.filter(announcement=a).count(), 1)
        self.assertEqual(a.read_records.count(), 1)

    def test_read_records_related_name(self):
        a = self._announcement()
        AnnouncementRead.objects.create(announcement=a, user=self.reader)
        self.assertEqual(a.read_records.filter(user=self.reader).count(), 1)
