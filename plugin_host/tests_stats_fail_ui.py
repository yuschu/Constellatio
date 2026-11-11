"""v1.7.12：前端接过 401 / 403（模板渲染层断言）。

**这是弱断言，不是行为验证**：项目没有 JS 测试基建，这里只保证「模板渲染成功 + 调用点接线正确」，
真正的行为（401 实际跳转到哪）靠容器实测（见 v1.7.12 文档 §五）。

两个关键点：
1. 每条用例先断言 200——项目有 `ExceptionGuardMiddleware`，模板语法错误（例如 include 里漏了
   `{% load i18n %}`）不会以 traceback 形式出现，而是变成 500，只断言页面里的字符串会把排查方向带偏。
2. 断言**调用点**而不是函数名：`handleStatsFailure` 这个字符串在 include 的函数定义里本来就有，
   只断言它出现，等于没锁住「fetch 分支被改回 throw」这种回退。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from plugins.user.models import Role

User = get_user_model()

BLOCKCHAIN_URL = '/plugins/blockchain/'
ATTENDANCE_URL = '/plugins/attendance/records/'


class StatsFailureUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user('stats_ui_mgr', password='pw')
        role = Role.objects.create(name='stats UI 管理岗')
        role.permissions.add(
            Permission.objects.get(codename='blockchain_view'),
            Permission.objects.get(codename='attendance_report_view'),
        )
        cls.manager.roles.add(role)

    def setUp(self):
        self.client.force_login(self.manager)

    def _assert_wired(self, url):
        """渲染成功 + fetch 分支真的调用了 handler + 旧写法已消失。"""
        response = self.client.get(url)
        # 第一条就验 500：模板语法错误会被 ExceptionGuardMiddleware 变成 500，
        # 若先断言字符串，诊断会指向「找不到某字符串」而不是「模板炸了」。
        self.assertEqual(response.status_code, 200, f'{url} 渲染失败（很可能是模板语法错误）')
        html = response.content.decode()
        # 调用点：`if (!response.ok) { handleStatsFailure(response); return null; }`
        # 用 regex 区分「函数定义」与「调用点」——定义处前缀是 function，不会命中这条。
        self.assertRegex(html, r'if \(!response\.ok\)\s*\{\s*handleStatsFailure\(response\)')
        self.assertNotIn("throw new Error('stats '", html)             # 旧写法已消失
        self.assertIn('handleStatsFailure', html)
        return html

    def test_blockchain_page_wires_handler(self):
        self._assert_wired(BLOCKCHAIN_URL)

    def test_attendance_page_wires_handler(self):
        self._assert_wired(ATTENDANCE_URL)

    def test_both_pages_share_same_include(self):
        """两页共用同一个 include：401/403 分支的文字与判据必须一致。"""
        first = self._assert_wired(BLOCKCHAIN_URL)
        second = self._assert_wired(ATTENDANCE_URL)
        marker = 'response.status === 401'
        self.assertIn(marker, first)
        self.assertIn(marker, second)

    def test_forbidden_copy_rendered(self):
        """403 分支的文案进了页面（且是通过 showEmpty('…') 的调用形式传的）。"""
        html = self._assert_wired(ATTENDANCE_URL)
        self.assertIn('showEmpty(', html)
        self.assertIn('无权查看该数据', html)
        self.assertIn('数据暂时不可用', html)

    def test_401_redirect_uses_page_url_not_stats_url(self):
        """401 跳转用的 next 必须来自 location.pathname，不能是 statsUrl（接口地址）。"""
        html = self._assert_wired(BLOCKCHAIN_URL)
        self.assertIn('window.location.pathname + window.location.search', html)
        self.assertNotIn('statsUrl + \'?next=', html)
