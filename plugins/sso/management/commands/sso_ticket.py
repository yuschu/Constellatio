"""签发企业 SSO Ticket（运维 / 联调 / 自动化测试用）。

用法：
    python manage.py sso_ticket alice
    python manage.py sso_ticket alice --name 张三 --email a@corp.com --ttl 120
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand

from plugins.sso.ticket import issue


class Command(BaseCommand):
    help = '签发企业 SSO 登录 Ticket（HMAC-SHA256）'

    def add_arguments(self, parser):
        parser.add_argument('username', help='登录用户名（不存在时按 SSO_AUTO_CREATE 自动建号）')
        parser.add_argument('--name', default='', help='姓名')
        parser.add_argument('--email', default='', help='邮箱')
        parser.add_argument('--department', default='', help='部门名称（可选）')
        parser.add_argument('--ttl', type=int, default=None,
                            help='有效期秒数（默认 SSO_TICKET_TTL）')

    def handle(self, *args, **options):
        payload = {
            'username': options['username'],
            'sub': options['username'],
            'iat': int(time.time()),
        }
        for key in ('name', 'email', 'department'):
            if options.get(key):
                payload[key] = options[key]
        ttl = options['ttl'] or getattr(settings, 'SSO_TICKET_TTL', 300)
        ticket = issue(payload, ttl=ttl)
        self.stdout.write(ticket)
        self.stderr.write(f'# {options["username"]} 有效期 {ttl}s')
