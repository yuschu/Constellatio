"""notice 单元测试：公告流展示 / 自动已读 / 已读人员 / 发布权限。

v1.6.11 起公告中心改为单列公告流：一次展示全部公告并自动登记已读，
不再有 ?notice= 内联详情、切换下拉和已读弹窗；旧详情链接改为锚点重定向。
因此本文件对 3 个断言旧交互的用例按新语义重写，并补齐公告流与已读人员覆盖。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

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

    def _grant_manage(self, user=None):
        user = user or self.publisher
        user.user_permissions.add(Permission.objects.get(codename='notice_manage'))
        return user

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

    def test_list_renders_all_titles_and_full_content(self):
        """新列表页一次展示全部公告：标题与正文都直接可见，不再只显示选中一条。"""
        self._announcement(title='第一篇', content='第一段正文开头\n补充说明')
        self._announcement(title='第二篇', content='第二段正文', is_top=True)
        self._announcement(title='第三篇', content='第三段正文')
        self.client.force_login(self.reader)

        response = self.client.get(reverse('notice:notice_list'))

        for title in ('第一篇', '第二篇', '第三篇'):
            self.assertContains(response, title)
        self.assertContains(response, '第一段正文开头')
        self.assertContains(response, '第二段正文')
        self.assertContains(response, '第三段正文')
        # 单列公告流：不再有左侧信息卡 / 切换公告 / 已读弹窗 / 返回列表
        self.assertNotContains(response, '公告信息')
        self.assertNotContains(response, '切换公告')
        self.assertNotContains(response, 'readers-modal')
        self.assertNotContains(response, '返回列表')

    def test_list_marks_all_read_once(self):
        """进入列表即自动把当前展示的全部公告记为已读，重复刷新不重复建。"""
        announcements = [self._announcement(title=f'公告{i}') for i in range(3)]
        self.client.force_login(self.reader)

        self.client.get(reverse('notice:notice_list'))
        first = AnnouncementRead.objects.filter(user=self.reader).count()
        self.assertEqual(first, len(announcements))
        self.assertEqual(
            set(AnnouncementRead.objects.filter(user=self.reader)
                .values_list('announcement_id', flat=True)),
            {a.id for a in announcements},
        )

        self.client.get(reverse('notice:notice_list'))
        self.assertEqual(
            AnnouncementRead.objects.filter(user=self.reader).count(), first)

    def test_normal_user_cannot_see_readers_link(self):
        """普通员工看不到「已读 N 人」入口，直接访问 readers 被 302 回首页。

        旧用例断言的是「?notice= 内联详情可访问」；该交互已删除，
        改为验证普通员工在公告流页面无已读人员入口且越权访问被拦截。
        """
        a = self._announcement(title='全员公告')
        self.client.force_login(self.reader)

        response = self.client.get(reverse('notice:notice_list'))
        self.assertNotContains(
            response, reverse('notice:notice_readers', args=[a.id]))
        self.assertNotContains(response, '已读 1 人')

        readers_url = reverse('notice:notice_readers', args=[a.id])
        self.assertRedirects(self.client.get(readers_url), reverse('index'))

    def test_manager_can_view_readers_page(self):
        """notice_manage 用户可见入口，readers 页 200 并列出已读用户。"""
        a = self._announcement(title='全员公告')
        AnnouncementRead.objects.create(announcement=a, user=self.reader)
        self._grant_manage()
        self.client.force_login(self.publisher)

        response = self.client.get(reverse('notice:notice_list'))
        self.assertContains(
            response, reverse('notice:notice_readers', args=[a.id]))
        # 列表页自动已读：publisher 本次访问也记为已读，故共 2 人
        self.assertContains(response, '已读 2 人')

        readers = self.client.get(reverse('notice:notice_readers', args=[a.id]))
        self.assertEqual(readers.status_code, 200)
        self.assertContains(readers, 'reader')
        self.assertContains(readers, '已读人员')

    def test_legacy_detail_redirects_to_anchor(self):
        """旧详情链接改为 302 到列表页锚点，不再渲染内容页（旧断言 Location 含 notice= 作废）。"""
        a = self._announcement(title='旧链接公告', content='旧链接正文')
        self.client.force_login(self.reader)

        legacy = self.client.get(f'/plugins/notice/{a.id}/')

        self.assertEqual(legacy.status_code, 302)
        self.assertEqual(
            legacy['Location'],
            f"{reverse('notice:notice_list')}#notice-{a.id}")
        self.assertTrue(legacy['Location'].endswith(f'#notice-{a.id}'))
        self.assertNotIn('notice=', legacy['Location'])

    def test_top_notice_renders_first(self):
        """重写原「默认选中第一条」用例：公告流里置顶公告仍排在最前并带置顶徽标。

        旧用例断言只显示置顶公告、不显示普通公告；新列表页全部展示，
        因此改为验证顺序（置顶在前）与徽标，而非「只显示一条」。
        """
        self._announcement(title='普通', content='普通正文')
        self._announcement(title='置顶', content='置顶正文', is_top=True)
        self.client.force_login(self.reader)

        response = self.client.get(reverse('notice:notice_list'))
        body = response.content.decode()

        self.assertContains(response, '置顶正文')
        self.assertContains(response, '普通正文')
        self.assertLess(body.index('置顶正文'), body.index('普通正文'))
        self.assertContains(response, 'r-badge')

    def test_create_announcement_redirects_to_list(self):
        """发布成功后回到公告流列表页（不再带 ?notice= 选中参数）。"""
        self._grant_manage()
        self.client.force_login(self.publisher)

        response = self.client.post(reverse('notice:notice_create'), {
            'title': '新公告', 'content': '新公告正文',
        })

        self.assertRedirects(response, reverse('notice:notice_list'))
        announcement = Announcement.objects.get(title='新公告')
        self.assertEqual(announcement.publisher, self.publisher)

    def test_create_requires_manage_perm(self):
        """无 notice_manage 的普通员工不能发布公告，POST 被 302 回首页。"""
        self.client.force_login(self.reader)

        response = self.client.post(reverse('notice:notice_create'), {
            'title': '越权公告', 'content': '越权正文',
        })

        self.assertRedirects(response, reverse('index'))
        self.assertFalse(Announcement.objects.filter(title='越权公告').exists())
