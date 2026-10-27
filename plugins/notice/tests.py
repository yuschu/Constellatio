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

    def test_normal_user_can_see_menu_and_detail(self):
        """公告对所有登录用户可见：无 notice_view 也能看到菜单和内联详情。"""
        a = self._announcement()
        self.client.force_login(self.reader)
        home = self.client.get('/')
        self.assertContains(home, '公告中心')
        self.assertEqual(self.client.get('/plugins/notice/').status_code, 200)
        self.assertEqual(
            self.client.get('/plugins/notice/', {'notice': a.id}).status_code, 200)

    def test_inline_detail_switch_and_read_mark(self):
        """v1.6.10：列表页内联详情，切换公告只换主体内容，旧详情链接重定向。"""
        first = self._announcement(title='第一篇', content='正文一')
        second = self._announcement(title='第二篇', content='正文二')
        self.client.force_login(self.reader)

        response = self.client.get('/plugins/notice/', {'notice': first.id})
        self.assertContains(response, '正文一')
        self.assertNotContains(response, '正文二')
        self.assertTrue(AnnouncementRead.objects.filter(
            announcement=first, user=self.reader).exists())

        response = self.client.get('/plugins/notice/', {'notice': second.id})
        self.assertContains(response, '正文二')
        self.assertNotContains(response, '正文一')

        legacy = self.client.get(f'/plugins/notice/{first.id}/')
        self.assertEqual(legacy.status_code, 302)
        self.assertIn(f'notice={first.id}', legacy['Location'])

    def test_default_selection_is_first_announcement(self):
        """未指定 notice 时默认展示排序第一条（置顶优先）。"""
        self._announcement(title='普通', content='普通正文')
        top = self._announcement(title='置顶', content='置顶正文', is_top=True)
        self.client.force_login(self.reader)
        response = self.client.get('/plugins/notice/')
        self.assertContains(response, '置顶正文')
        self.assertNotContains(response, '普通正文')
        self.assertTrue(AnnouncementRead.objects.filter(
            announcement=top, user=self.reader).exists())

