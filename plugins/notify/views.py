"""notify 插件视图：消息中心 / 已读 / 全部已读。"""

from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from plugin_host.permissions import require_perm

from .models import Notification


@require_perm('notify_view')
def notify_list(request):
    """消息中心：全部 / 未读筛选（仅本人消息）。"""
    status = (request.GET.get('status') or '').strip()
    items = Notification.objects.filter(recipient=request.user)
    if status == 'unread':
        items = items.filter(is_read=False)
    unread = Notification.objects.filter(
        recipient=request.user, is_read=False).count()
    return render(request, 'notify/notify_list.html', {
        'notifications': items.order_by('-created_at')[:200],
        'unread': unread,
        'status': status,
    })


@require_perm('notify_view')
def notify_read(request, pk):
    """标记单条已读并跳转业务链接（仅内部链接）。"""
    notification = get_object_or_404(
        Notification, pk=pk, recipient=request.user)
    if not notification.is_read:
        Notification.objects.filter(pk=notification.pk).update(
            is_read=True, read_at=timezone.now())
    target = notification.link or ''
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return redirect(target)
    return redirect('notify:notify_list')


@require_POST
@require_perm('notify_view')
def notify_read_all(request):
    Notification.objects.filter(
        recipient=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now())
    return redirect('notify:notify_list')
