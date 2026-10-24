"""notice 插件视图：公告列表 + 内联详情 / 已读 / 发布（v1.6.10）。"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from plugin_host.signals import notice_published

from .models import Announcement, AnnouncementRead


@login_required
def notice_list(request):
    """公告中心：列表 + 当前页内联详情，切换公告不跳新页面。"""
    selected_pk = (request.GET.get('notice') or '').strip()
    selected_pk = int(selected_pk) if selected_pk.isdigit() else None
    if selected_pk is not None:
        if not Announcement.objects.filter(pk=selected_pk).exists():
            raise Http404('公告不存在')
    else:
        first = Announcement.objects.order_by('-is_top', '-created_at').first()
        selected_pk = first.pk if first else None

    if selected_pk is not None:
        AnnouncementRead.objects.get_or_create(
            announcement_id=selected_pk, user=request.user)

    announcements = list(
        Announcement.objects.annotate(read_count=Count('read_records')))
    selected = next((item for item in announcements if item.pk == selected_pk), None)
    readers = []
    if selected is not None:
        readers = list(AnnouncementRead.objects.filter(announcement=selected)
                       .select_related('user').order_by('-read_at'))
    read_ids = set(AnnouncementRead.objects.filter(
        user=request.user).values_list('announcement_id', flat=True))

    return render(request, 'notice/notice_list.html', {
        'announcements': announcements,
        'selected': selected,
        'readers': readers,
        'read_ids': read_ids,
    })


@login_required
def notice_detail(request, pk):
    """兼容旧详情链接：重定向到列表页内联详情（不再单独页面）。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    return redirect(f"{reverse('notice:notice_list')}?notice={announcement.pk}")


@login_required
def notice_create(request):
    """发布公告（需 notice_manage 权限），发布即发信号。"""
    if not request.user.has_perm('notice_manage'):
        return redirect('index')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '')
        if title and content:
            announcement = Announcement.objects.create(
                title=title, content=content, publisher=request.user,
                is_top=request.POST.get('is_top') == 'on')
            notice_published.send(sender=announcement.__class__, announcement_id=announcement.id)
            return redirect(f"{reverse('notice:notice_list')}?notice={announcement.id}")
    return render(request, 'notice/notice_form.html')
