"""SSO Ticket 校验 / 登录 / 自动建号测试。"""

import time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from .ticket import TicketError, issue, verify

User = get_user_model()
SECRET = 'test-sso-secret'


@override_settings(SSO_SHARED_SECRET=SECRET, SSO_TICKET_TTL=300, SSO_AUTO_CREATE=True)
class SsoTicketTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_roundtrip(self):
        ticket = issue({'username': 'alice', 'name': '张三'})
        payload = verify(ticket)
        self.assertEqual(payload['username'], 'alice')
        self.assertEqual(payload['name'], '张三')
        self.assertIn('exp', payload)

    def test_tampered_signature_rejected(self):
        ticket = issue({'username': 'alice'})
        bad = ticket[:-2] + ('AA' if not ticket.endswith('AA') else 'BB')
        with self.assertRaises(TicketError):
            verify(bad)

    def test_expired_rejected(self):
        ticket = issue({'username': 'alice'}, ttl=1)
        with self.assertRaises(TicketError):
            verify(ticket, now=int(time.time()) + 10)

    def test_replay_rejected(self):
        ticket = issue({'username': 'alice'})
        verify(ticket)
        with self.assertRaises(TicketError):
            verify(ticket)

    def test_malformed_rejected(self):
        for bad in ('', 'abc', 'a.b.c', 'x.y'):
            with self.subTest(ticket=bad), self.assertRaises(TicketError):
                verify(bad)


@override_settings(SSO_SHARED_SECRET=SECRET, SSO_TICKET_TTL=300, SSO_AUTO_CREATE=True)
class SsoLoginTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_auto_create_and_login(self):
        ticket = issue({'username': 'sso_alice', 'name': '艾丽丝', 'email': 'a@corp.com'})
        response = self.client.get('/plugins/sso/login/', {'ticket': ticket, 'next': '/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')
        user = User.objects.get(username='sso_alice')
        self.assertEqual(user.last_name, '艾丽丝')
        self.assertEqual(user.email, 'a@corp.com')
        self.assertFalse(user.has_usable_password())
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_existing_user_login(self):
        user = User.objects.create_user('sso_bob', password='pw')
        ticket = issue({'username': 'sso_bob'})
        response = self.client.get('/plugins/sso/login/', {'ticket': ticket})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_disabled_user_rejected(self):
        user = User.objects.create_user('sso_disabled', password='pw', is_active=False)
        ticket = issue({'username': 'sso_disabled'})
        response = self.client.get('/plugins/sso/login/', {'ticket': ticket})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '账号已禁用')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_invalid_ticket_shows_error(self):
        response = self.client.get('/plugins/sso/login/', {'ticket': 'bad.ticket'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ticket')

    def test_open_redirect_blocked(self):
        ticket = issue({'username': 'sso_next'})
        response = self.client.get(
            '/plugins/sso/login/', {'ticket': ticket, 'next': 'https://evil.example.com/'})
        self.assertEqual(response['Location'], '/')

    @override_settings(SSO_AUTO_CREATE=False)
    def test_auto_create_disabled(self):
        ticket = issue({'username': 'sso_new'})
        response = self.client.get('/plugins/sso/login/', {'ticket': ticket})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='sso_new').exists())

    def test_management_command_issues_usable_ticket(self):
        import io
        from django.core.management import call_command
        out = io.StringIO()
        call_command('sso_ticket', 'sso_cmd', '--name', '命令行', stdout=out)
        ticket = out.getvalue().strip()
        payload = verify(ticket)
        self.assertEqual(payload['username'], 'sso_cmd')
