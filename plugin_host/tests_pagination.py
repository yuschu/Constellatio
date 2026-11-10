"""v1.7.6 分页：公共分页入口 + 筛选参数保留 + 公告增量登记 + 留痕翻页。

断言落在「行为」而不是「恰好几次查询」：
- 页大小 / 越界 / 参数保留 / 增量登记，直接看响应内容与数据库行数；
- 只有「二次进入公告中心不再插入」用 `CaptureQueriesContext` 数 INSERT，
  且只断言通知表的 INSERT 条数，不钉死总查询数。
"""

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from plugin_host.pagination import DEFAULT_PAGE_SIZE
from plugins.attendance.models import Attendance
from plugins.blockchain.models import BlockchainRecord
from plugins.notice.models import Announcement, AnnouncementRead

User = get_user_model()


class _AdminMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('page_admin', '', 'PageAdmin@2026')

    def setUp(self):
        self.client.force_login(self.admin)


class BlockchainPaginationTests(_AdminMixin, TestCase):
    """留痕：50/页、总数可见、越界回落末页、能翻到旧记录。"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.records = [
            BlockchainRecord.append('attendance', 'attendance_checked', f'attendance:{i}')
            for i in range(60)
        ]
        cls.oldest = cls.records[0]

    @staticmethod
    def _detail_links(body):
        return re.findall(r'/plugins/blockchain/(\d+)/', body)

    def test_page_size_applies(self):
        response = self.client.get('/plugins/blockchain/')
        self.assertEqual(response.status_code, 200)
        page_obj = response.context['page_obj']
        self.assertEqual(page_obj.paginator.count, 60)
        self.assertEqual(len(page_obj.object_list), 50)          # 单页 50 行
        self.assertEqual(page_obj.paginator.num_pages, 2)
        body = response.content.decode()
        self.assertEqual(len(set(self._detail_links(body))), 50)  # 只渲染本页
        self.assertIn('共 60 条', body)                           # 总数照旧显示

    def test_out_of_range_page_falls_back_to_last(self):
        response = self.client.get('/plugins/blockchain/', {'page': '999'})
        self.assertEqual(response.status_code, 200)
        page_obj = response.context['page_obj']
        self.assertEqual(page_obj.number, page_obj.paginator.num_pages)
        self.assertEqual(len(page_obj.object_list), 10)           # 60 - 50

    def test_pagination_reaches_old_records(self):
        first = self.client.get('/plugins/blockchain/').content.decode()
        self.assertNotIn('/plugins/blockchain/%d/' % self.oldest.pk, first)
        second = self.client.get('/plugins/blockchain/', {'page': '2'}).content.decode()
        self.assertIn('/plugins/blockchain/%d/' % self.oldest.pk, second)


class QueryParamPreservationTests(_AdminMixin, TestCase):
    """翻页链接必须带上原有筛选参数（旧实现是裸 ?page=N，会整体覆盖 query string）。"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        today = timezone.localdate()
        # 签到详情默认时间范围是「本月至今」，所以造数据要落在当月内：
        # 3 个员工 × 10 天 = 30 条（一人一天一条是唯一约束），确保能翻到第 2 页。
        staff = [cls.admin] + [
            User.objects.create_user(f'page_staff{i}', password='pw') for i in (1, 2)]
        for user in staff:
            for day in range(10):
                Attendance.objects.create(
                    user=user, date=today - timedelta(days=day),
                    status=Attendance.Status.LATE,
                    sign_type=Attendance.SignType.INTERNAL,
                    check_in=timezone.now() - timedelta(days=day))

    def test_pager_keeps_filter_params(self):
        page1 = self.client.get('/plugins/attendance/records/', {'status': 'late'})
        self.assertEqual(page1.status_code, 200)
        body1 = page1.content.decode()
        self.assertIn('status=late', body1)      # 下一页链接带筛选参数
        self.assertIn('page=2', body1)

        page2 = self.client.get(
            '/plugins/attendance/records/', {'status': 'late', 'page': '2'})
        body2 = page2.content.decode()
        # 上一页回第 1 页时删掉 page 参数，但保留 status（不是 ?page=1）
        self.assertIn('href="?status=late"', body2)


class NoticeIncrementalReadTests(TestCase):
    """公告中心：只登记当页未读；二次进入零插入。"""

    @classmethod
    def setUpTestData(cls):
        cls.publisher = User.objects.create_user('page_pub', password='pw')
        cls.reader = User.objects.create_user('page_reader', password='pw')
        cls.announcements = [
            Announcement.objects.create(
                title=f'公告{i}', content=f'正文{i}', publisher=cls.publisher)
            for i in range(DEFAULT_PAGE_SIZE + 5)         # 30 条 > 一页
        ]

    def test_only_current_page_is_registered(self):
        self.client.force_login(self.reader)
        response = self.client.get('/plugins/notice/')
        self.assertEqual(response.status_code, 200)
        page_obj = response.context['page_obj']
        self.assertEqual(len(page_obj.object_list), DEFAULT_PAGE_SIZE)

        registered = AnnouncementRead.objects.filter(user=self.reader).count()
        self.assertEqual(registered, DEFAULT_PAGE_SIZE)   # 只登记当页，不是全部 30 条
        self.assertEqual(
            set(AnnouncementRead.objects.filter(user=self.reader)
                .values_list('announcement_id', flat=True)),
            {item.pk for item in page_obj.object_list})

        self.client.get('/plugins/notice/', {'page': '2'})   # 第 2 页把剩下 5 条登记掉
        self.assertEqual(
            AnnouncementRead.objects.filter(user=self.reader).count(), len(self.announcements))

    def test_second_visit_inserts_nothing(self):
        self.client.force_login(self.reader)
        self.assertEqual(AnnouncementRead.objects.filter(user=self.reader).count(), 0)

        def notice_inserts():
            with CaptureQueriesContext(connection) as captured:
                self.client.get('/plugins/notice/')
            # 注意 sqlite 下 bulk_create(ignore_conflicts=True) 生成的是 INSERT OR IGNORE，
            # 所以只匹配 'INSERT' + 表名，不写死 'INSERT INTO'
            return [q for q in captured.captured_queries
                    if 'INSERT' in q['sql'] and 'notice_announcementread' in q['sql']]

        self.assertEqual(len(notice_inserts()), 1)     # 首次：一条 bulk_create 登记当页
        self.assertEqual(len(notice_inserts()), 0)     # 二次：零插入
        self.assertEqual(
            AnnouncementRead.objects.filter(user=self.reader).count(), DEFAULT_PAGE_SIZE)


class UserListPaginationTests(_AdminMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for i in range(30):
            User.objects.create_user(f'page_u{i}', password='pw')

    def test_user_list_paginates(self):
        response = self.client.get('/plugins/user/users/')
        self.assertEqual(response.status_code, 200)
        page_obj = response.context['page_obj']
        self.assertEqual(len(page_obj.object_list), DEFAULT_PAGE_SIZE)
        self.assertEqual(page_obj.paginator.count, 31)      # 30 + admin

        second = self.client.get('/plugins/user/users/', {'page': '2'})
        self.assertEqual(len(second.context['page_obj'].object_list), 31 - DEFAULT_PAGE_SIZE)
