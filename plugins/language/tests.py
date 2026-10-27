"""language 插件测试：默认中文 / Cookie 切换 / 安全跳转 / 翻译编译。"""

import gettext
import io

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from plugin_host.middleware import DefaultLanguageMiddleware
from tools.compile_mo import build_mo, compile_all, parse_po_text


class LanguageTestMixin:
    def tearDown(self):
        translation.deactivate()
        super().tearDown()


class DefaultLanguageMiddlewareTest(LanguageTestMixin, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = DefaultLanguageMiddleware(lambda request: HttpResponse())

    def _request(self, **cookies):
        request = self.factory.get('/', HTTP_ACCEPT_LANGUAGE='en-US')
        request.COOKIES.update(cookies)
        return request

    def test_default_is_chinese_even_if_browser_is_english(self):
        request = self._request()
        self.middleware.process_request(request)
        self.assertEqual(translation.get_language(), 'zh-hans')

    def test_cookie_en_activates_english(self):
        request = self._request(django_language='en')
        self.middleware.process_request(request)
        self.assertEqual(translation.get_language(), 'en')

    def test_invalid_cookie_falls_back_to_chinese(self):
        request = self._request(django_language='fr')
        self.middleware.process_request(request)
        self.assertEqual(translation.get_language(), 'zh-hans')


class LanguageSwitchViewTest(LanguageTestMixin, TestCase):
    url = '/plugins/language/switch/'

    def test_post_en_sets_persistent_cookie(self):
        response = self.client.post(self.url, {'lang': 'en', 'next': '/plugins/notice/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/plugins/notice/')
        cookie = response.cookies['django_language']
        self.assertEqual(cookie.value, 'en')
        # v1.5.7：持久 Cookie（默认 1 年）——“最后设置的语言”在插件停用后仍生效
        self.assertEqual(int(cookie['max-age']), settings.LANGUAGE_COOKIE_AGE)
        self.assertTrue(cookie['max-age'])

    def test_post_invalid_lang_does_not_set_cookie(self):
        response = self.client.post(self.url, {'lang': 'fr'})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('django_language', response.cookies)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_external_next_blocked(self):
        response = self.client.post(self.url, {'lang': 'en', 'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], '/')

    def test_internal_next_kept(self):
        response = self.client.post(self.url, {'lang': 'en', 'next': '/plugins/notice/'})
        self.assertEqual(response['Location'], '/plugins/notice/')

    def test_anonymous_can_switch(self):
        response = self.client.post(self.url, {'lang': 'en'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies['django_language'].value, 'en')

    def test_language_is_not_required_plugin(self):
        """v1.5.7：语言插件不再是系统必需，可被管理员停用。"""
        from plugins.workspace.views import PROTECTED
        self.assertNotIn('language', PROTECTED)
        self.assertEqual(PROTECTED, {'workspace'})


class LanguagePluginDisableTest(LanguageTestMixin, TestCase):
    """v1.5.7：language 停用 → 只收走切换入口，沿用最后设置的语言。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('langoff', password='pw')

    def _disable(self):
        from plugins.workspace.models import PluginSwitch
        PluginSwitch.objects.update_or_create(
            app_key='language', defaults={'enabled': False})

    def test_enabled_plugin_renders_switch_entry(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'en'
        resp = self.client.get('/')
        self.assertContains(resp, '/plugins/language/switch/')

    def test_disabled_keeps_last_language_and_hides_entry(self):
        self._disable()
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'en'
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Workspace')                      # 仍为最后设置的语言
        self.assertNotContains(resp, '/plugins/language/switch/')    # 入口已收起

    def test_disabled_switch_route_404(self):
        self._disable()
        resp = self.client.post('/plugins/language/switch/', {'lang': 'en'})
        self.assertEqual(resp.status_code, 404)

    def test_disabled_plugin_toggleable_from_switch_page(self):
        from plugins.workspace.models import PluginSwitch
        admin = get_user_model().objects.create_superuser('langadmin', '', 'pw')
        self.client.force_login(admin)
        resp = self.client.post('/plugins/workspace/language/toggle/', {'enabled': '0'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PluginSwitch.objects.get(app_key='language').enabled)


class TranslationCatalogTest(LanguageTestMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compile_all()

    def test_menu_label_translates(self):
        with translation.override('en'):
            self.assertEqual(str(_('工作台')), 'Workspace')
            self.assertEqual(str(_('审批中心')), 'Approvals')
            self.assertEqual(str(_('插件开关')), 'Plugin switches')
            self.assertEqual(str(_('加载中…')), 'Loading…')

    def test_rendered_home_is_english(self):
        user = get_user_model().objects.create_user('languser', password='pw')
        self.client.force_login(user)
        self.client.cookies['django_language'] = 'en'
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Workspace')
        self.assertContains(response, 'Everything is a plugin')


class CompileMoTest(TestCase):
    def test_parse_and_build_mo(self):
        text = '''msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8"

msgid "工作台"
msgstr "Workspace"

msgid "多行"
msgstr ""
"Line one "
"Line two"

#, fuzzy
msgid "忽略"
msgstr "Ignore"
'''
        header, entries = parse_po_text(text)
        self.assertEqual(entries['工作台'], 'Workspace')
        self.assertEqual(entries['多行'], 'Line one Line two')
        self.assertNotIn('忽略', entries)
        catalog = gettext.GNUTranslations(io.BytesIO(build_mo(header, entries)))
        self.assertEqual(catalog.gettext('工作台'), 'Workspace')
        self.assertEqual(catalog.gettext('多行'), 'Line one Line two')
        self.assertEqual(catalog.gettext('忽略'), '忽略')
