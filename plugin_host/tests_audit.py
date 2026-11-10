"""v1.7.8 审计字段：中间件 + pre_save 自动填充的七条行为用例。

分工：
- HTTP 新建走真实中间件栈（`Client`）；
- 更新 / 异常复位 / 显式传值 / 匿名这些没有现成表单入口的路径，用 `RequestFactory` + 直接调用
  `CurrentUserMiddleware`（等价于走一遍中间件，但不依赖具体视图）。
- sqlite 上 `select_for_update` 之类的并发语义不在这里验证（与本版无关）。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.utils import timezone

from plugin_host.current_user import get_current_user
from plugin_host.middleware import CurrentUserMiddleware
from plugins.notice.models import Announcement
from plugins.structure.models import StructureRecord

User = get_user_model()


def run_in_request(user, func):
    """用 CurrentUserMiddleware 包一层，模拟「某个用户在请求里执行 func」。"""
    request = RequestFactory().get('/audit-test/')
    request.user = user
    return CurrentUserMiddleware(lambda _request: func())(request)


class AuditFillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_superuser('audit_alice', '', 'AuditAlice@2026')
        cls.bob = User.objects.create_user('audit_bob', password='AuditBob@2026')

    def test_http_create_sets_created_by(self):
        """走真实 HTTP：新建公告 → created_by / updated_by 都是当前用户。"""
        self.client.force_login(self.alice)
        response = self.client.post(
            '/plugins/notice/new/', {'title': '审计用例', 'content': '正文'})
        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get(title='审计用例')
        self.assertEqual(announcement.created_by_id, self.alice.pk)
        self.assertEqual(announcement.updated_by_id, self.alice.pk)

    def test_update_sets_updated_by_keeps_created_by(self):
        """换一个用户保存同一行：updated_by 变、created_by 不变。"""
        announcement = run_in_request(self.alice, lambda: Announcement.objects.create(
            title='更新用例', content='正文', publisher=self.alice))
        self.assertEqual(announcement.created_by_id, self.alice.pk)

        def save_as_bob():
            announcement.title = '更新用例-改'
            announcement.save()
            return announcement

        saved = run_in_request(self.bob, save_as_bob)
        self.assertEqual(saved.created_by_id, self.alice.pk)    # 创建人不变
        self.assertEqual(saved.updated_by_id, self.bob.pk)      # 更新人变

    def test_no_request_context_gives_null(self):
        """无中间件（manage.py shell / 后台线程）：字段为 NULL 且不报错。"""
        announcement = Announcement.objects.create(
            title='后台用例', content='正文', publisher=self.alice)
        self.assertIsNone(announcement.created_by_id)
        self.assertIsNone(announcement.updated_by_id)

    def test_context_reset_on_exception(self):
        """异常路径也要复位 contextvar：抛错后同一线程再写库不应带上旧用户。"""
        def boom():
            raise RuntimeError('boom in view')

        with self.assertRaises(RuntimeError):
            run_in_request(self.alice, boom)
        self.assertIsNone(get_current_user())

        after = Announcement.objects.create(title='异常后', content='正文', publisher=self.alice)
        self.assertIsNone(after.created_by_id)

        def as_bob():
            return Announcement.objects.create(title='异常后-B', content='正文', publisher=self.bob)

        second = run_in_request(self.bob, as_bob)
        self.assertEqual(second.created_by_id, self.bob.pk)

    def test_explicit_created_by_not_overwritten(self):
        """显式传了 created_by：尊重调用方，不被当前用户覆盖。"""
        def create_with_explicit_owner():
            return Announcement.objects.create(
                title='显式创建人', content='正文', publisher=self.alice,
                created_by=self.bob)

        announcement = run_in_request(self.alice, create_with_explicit_owner)
        self.assertEqual(announcement.created_by_id, self.bob.pk)
        # updated_by 仍按当前用户填
        self.assertEqual(announcement.updated_by_id, self.alice.pk)

    def test_anonymous_request_does_not_crash(self):
        """匿名请求写入：AnonymousUser 必须被映射成 None，不能抛 ValueError。"""
        announcement = run_in_request(
            AnonymousUser(),
            lambda: Announcement.objects.create(
                title='匿名路径', content='正文', publisher=self.alice))
        self.assertIsNone(announcement.created_by_id)
        self.assertIsNone(announcement.updated_by_id)

    def test_partial_save_update_fields_persists_updated_by(self):
        """`save(update_fields=[...])` 必须把 updated_by 落库（v1.7.8 收尾的 P1 回归）。

        生产代码 20 处更新全部走部分更新；`pre_save` 只改内存、改不了 UPDATE 列清单，
        所以在 `AuditModel.save()` 里统一把 updated_by / updated_at 并入 update_fields。
        这里用 `Department` 复现 `user/views.py` 的 `save(update_fields=['is_active', …])` 路径。
        """
        from plugins.user.models import Department

        dept = run_in_request(self.alice, lambda: Department.objects.create(name='审计部分更新'))
        self.assertEqual(Department.objects.get(pk=dept.pk).updated_by_id, self.alice.pk)

        def partial_update():
            dept.is_active = False
            dept.save(update_fields=['is_active'])
            return dept

        run_in_request(self.bob, partial_update)
        # 关键：查 DB，不看内存（内存值不代表已落库）
        fresh = Department.objects.get(pk=dept.pk)
        self.assertEqual(fresh.updated_by_id, self.bob.pk)
        self.assertEqual(fresh.created_by_id, self.alice.pk)

    def test_partial_save_also_touches_updated_at(self):
        """部分更新同样要刷新 updated_at —— 生产里有 5 处调用连 updated_at 都漏了。"""
        from plugins.user.models import Department

        dept = run_in_request(self.alice, lambda: Department.objects.create(name='审计时间戳'))
        before = Department.objects.get(pk=dept.pk).updated_at

        def partial_update():
            dept.is_active = False
            dept.save(update_fields=['is_active'])

        run_in_request(self.bob, partial_update)
        after = Department.objects.get(pk=dept.pk).updated_at
        self.assertGreater(after, before)

    def test_current_user_middleware_after_authentication(self):
        """位置护栏：CurrentUserMiddleware 必须在 AuthenticationMiddleware 之后。

        否则 `request.user` 还不存在 → 审计字段全 NULL，而且不报错、测试也不会红。
        """
        from django.conf import settings

        middleware = list(settings.MIDDLEWARE)
        self.assertIn('plugin_host.middleware.CurrentUserMiddleware', middleware)
        auth_index = middleware.index('django.contrib.auth.middleware.AuthenticationMiddleware')
        current_index = middleware.index('plugin_host.middleware.CurrentUserMiddleware')
        self.assertLess(auth_index, current_index)

    def test_structure_excluded_from_audit(self):
        """structure 明确不纳入：没有 created_at/created_by 列，只有 applied_at/applied_by。"""
        field_names = {field.name for field in StructureRecord._meta.get_fields()}
        self.assertIn('applied_at', field_names)
        self.assertIn('applied_by', field_names)
        for absent in ('created_at', 'updated_at', 'created_by', 'updated_by'):
            self.assertNotIn(absent, field_names)
        # 也不允许用 property 伪装
        record = StructureRecord(applied_by=self.alice, applied_at=timezone.now())
        for alias in ('created_at', 'updated_at', 'created_by', 'updated_by'):
            self.assertFalse(hasattr(record, alias), f'{alias} 不应存在（包括 property 别名）')
