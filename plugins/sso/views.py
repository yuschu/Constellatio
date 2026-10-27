"""企业 SSO 登录：校验网关 Ticket → 关联 / 自动建号 → 登录。"""

from django.apps import apps as dj_apps
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie

from plugin_host.signals import sso_login, user_created

from .ticket import TicketError, verify


def _safe_next(request, value):
    value = value or '/'
    if url_has_allowed_host_and_scheme(
            value, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return value
    return '/'


def _resolve_user(payload):
    """Ticket → (user, auto_created)；无用户名返回 (None, False)。"""
    User = get_user_model()
    username = (payload.get('username') or payload.get('sub') or '').strip()
    if not username:
        return None, False
    user = User.objects.filter(username=username).first()
    if user is not None:
        return user, False
    if not getattr(settings, 'SSO_AUTO_CREATE', True):
        return None, False

    user = User.objects.create_user(
        username=username,
        email=(payload.get('email') or '')[:254],
        password=None,   # 不可用密码：SSO 账号仅能通过 Ticket 登录
    )
    update_fields = []
    name = (payload.get('name') or '')[:150]
    if name:
        user.last_name = name
        update_fields.append('last_name')
    department_name = (payload.get('department') or '').strip()
    if department_name:
        try:
            Department = dj_apps.get_model('user', 'Department')
            department = Department.objects.filter(
                name=department_name, is_active=True).first()
        except LookupError:
            department = None
        if department is not None:
            user.department = department
            update_fields.append('department')
    if update_fields:
        user.save(update_fields=update_fields)
    user_created.send(sender=user.__class__, user_id=user.pk)
    return user, True


@ensure_csrf_cookie
def sso_login_view(request):
    """GET/POST /plugins/sso/login/?ticket=...：企业门户跳转入口 + 手工 Ticket 表单。"""
    next_url = _safe_next(
        request, request.POST.get('next') or request.GET.get('next'))
    ticket = (request.POST.get('ticket') or request.GET.get('ticket') or '').strip()
    error = None

    if ticket:
        try:
            payload = verify(ticket)
        except TicketError as exc:
            error = str(exc)
        else:
            user, auto_created = _resolve_user(payload)
            if user is None:
                error = _('Ticket 缺少用户名')
            elif not user.is_active:
                error = _('账号已禁用，无法登录')
            else:
                login(request, user,
                      backend='django.contrib.auth.backends.ModelBackend')
                sso_login.send(
                    sender=user.__class__, user_id=user.pk,
                    via='ticket', auto_created=auto_created)
                return redirect(next_url)

    return render(request, 'sso/sso_login.html', {
        'error': error,
        'next': next_url,
        'ticket': ticket,
    })


def sso_entry(request):
    """登录页按钮入口：无 Ticket 时展示企业 SSO 说明。"""
    if request.user.is_authenticated:
        return redirect('index')
    return render(request, 'sso/sso_login.html', {
        'error': None,
        'next': _safe_next(request, request.GET.get('next')),
        'ticket': '',
    })
