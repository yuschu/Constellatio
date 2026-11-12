"""auth 插件：统一登录 / 登出（认证后端走 Django auth，可插拔）。

v1.7.1（P1-14）：登录失败计数限流——同一「用户名 + 来源 IP」在窗口内
连续失败达到阈值后，即使密码正确也先拒绝，避免在线爆破。
v1.7.7（P2）：计数从共享缓存（get + set 两步，多 worker 会丢更新）改为独立计数表
+ `select_for_update()` 行锁；sqlite 上 select_for_update 静默退化，
并发语义只在 MySQL 上成立（与 v1.7.1 区块链链尾锁同一口径）。
"""

import hashlib
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required
from django.db import IntegrityError, OperationalError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .models import LoginFailureCounter

# 失败阈值与窗口（秒）：5 次 / 15 分钟
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW = 900


def _client_ip(request):
    """限流维度取 REMOTE_ADDR：不信任可伪造的 X-Forwarded-For。

    若部署在反代之后需要按真实客户端计数，应在反代侧改写 REMOTE_ADDR
    （gunicorn --forwarded-allow-ips + ProxyFix），而不是在这里读请求头。
    """
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _fail_key(request, username):
    """失败计数键：用户名 + IP 一起哈希，避免明文用户名进库（与旧缓存键同源算法）。"""
    raw = f'{(username or "").lower()}|{_client_ip(request)}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]


def _window_cutoff(now):
    return now - timedelta(seconds=LOGIN_FAIL_WINDOW)


def _failure_count(request, username, now=None):
    """当前窗口内的失败次数；无行或窗口已过期都算 0（读路径不需要加锁）。"""
    now = now or timezone.now()
    row = (LoginFailureCounter.objects
           .filter(key=_fail_key(request, username))
           .values_list('count', 'window_started_at').first())
    if row is None:
        return 0
    count, started = row
    return 0 if started <= _window_cutoff(now) else count


def _is_locked(request, username):
    return _failure_count(request, username) >= LOGIN_FAIL_LIMIT


def _is_deadlock(exc):
    """MySQL InnoDB 死锁（errno 1213）。

    高并发下这是**正常现象**，标准处置是重试事务（而不是把 500 甩给用户）。
    实测踩过：对「尚不存在」的 key 做 `SELECT ... FOR UPDATE` 会加 gap 锁，
    与并发的 INSERT 互相等待 → 1213。
    """
    args = getattr(exc, 'args', ())
    return bool(args) and args[0] == 1213


def _bump_counter(key):
    """把某个 key 的失败次数 +1（窗口内）或重置为 1（过期）。

    关键：**只对已存在的行加行锁**。对不存在的 key 直接 `select_for_update()` 会加
    gap 锁并与并发 INSERT 死锁；所以先做无锁 exists 判断，插入靠唯一键兜并发，
    只有行确实存在时才 `select_for_update()` 取记录锁。
    """
    now = timezone.now()
    cutoff = _window_cutoff(now)
    if not LoginFailureCounter.objects.filter(key=key).exists():
        try:
            LoginFailureCounter.objects.create(key=key, count=1, window_started_at=now)
            return 1
        except IntegrityError:
            pass                    # 并发下别人先插入了 → 落到下面按已存在处理

    # 约束 1：select_for_update() 的 queryset 不能带切片（支持 FOR UPDATE 的后端上
    #         「FOR UPDATE + LIMIT/OFFSET」会 NotSupportedError；sqlite 上被静默忽略，不易发现）
    # 约束 2：必须在 transaction.atomic() 内调用，否则 MySQL 抛 TransactionManagementError
    with transaction.atomic():
        counter = LoginFailureCounter.objects.select_for_update().get(key=key)
        if counter.window_started_at <= cutoff:
            counter.count = 1
            counter.window_started_at = now
        elif counter.count >= LOGIN_FAIL_LIMIT:
            # 已达阈值：不再累加、也不刷新窗口（否则持续爆破会把窗口无限延长）。
            # 这样 6 路并发突发时计数最多就是 5，第 6 次落到调用方按「已锁定」处理。
            return counter.count
        else:
            counter.count += 1
        counter.save(update_fields=['count', 'window_started_at'])
        return counter.count


def _record_failure(request, username):
    """记一次失败：失败计数跨 worker 不丢更新（死锁重试最多 3 次）。"""
    key = _fail_key(request, username)
    for attempt in range(3):
        try:
            return _bump_counter(key)
        except OperationalError as exc:
            if not _is_deadlock(exc) or attempt == 2:
                raise
            # 死锁：InnoDB 已回滚本事务，直接重试
    raise AssertionError('unreachable')


def _next_target(request):
    """v1.7.4 收尾：取登录后要回跳的地址（POST 优先，其次 GET）。

    只返回同站地址；外站与协议相对 URL（`//evil.com`）一律丢弃返回空串。
    校验口径与 Django `LoginView` 的 `SuccessURLAllowedHostsMixin` 一致。
    """
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return ''


def _redirect_after_login(request):
    """登录成功（或已登录用户访问登录页）后：有合法 next 就回原页，否则回工作台。"""
    target = _next_target(request)
    return redirect(target) if target else redirect('index')


@login_not_required        # v1.7.4：匿名入口（否则 LoginRequiredMiddleware 造成无限重定向）
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_after_login(request)

    error = None
    username = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if _is_locked(request, username):
            error = _('尝试次数过多，请稍后再试')
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                LoginFailureCounter.objects.filter(key=_fail_key(request, username)).delete()
                login(request, user)
                return _redirect_after_login(request)
            failures = _record_failure(request, username)
            # 并发突发时，「锁定」可能是在本次累加后才达成的（检查发生在 authenticate 之前），
            # 所以这里用本次返回值判定：达到阈值当次就提示锁定，不等到下一次请求。
            if failures >= LOGIN_FAIL_LIMIT:
                error = _('尝试次数过多，请稍后再试')
            else:
                error = _('用户名或密码错误')

    # 失败时回填用户名；密码出于安全不回填。
    # next 必须传进上下文，否则模板里的隐藏域渲染成空串、回跳形同虚设（v1.7.4 收尾）。
    return render(request, 'login.html', {
        'error': error,
        'username': username,
        'next': _next_target(request),
    })


@login_not_required        # v1.7.4：未登录点「退出」不该被跳去登录页
@require_POST              # v1.7.15 / 7.3：GET 登出可被 <img src> 之类跨站触发，改 POST + CSRF
def logout_view(request):
    logout(request)
    return redirect('index')


@login_not_required        # v1.7.4：登录页「忘记密码」入口，匿名可达
def password_reset_notice(request):
    """密码重置占位页：v1.5 只提供入口，不发送邮件、不伪造重置。"""
    return render(request, 'auth/password_reset_notice.html')
