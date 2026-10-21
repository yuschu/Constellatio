"""notice 插件视图：公告列表 / 详情已读 / 发布。"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from plugin_host.signals import notice_published

from .models import Announcement, AnnouncementRead


@login_required
def notice_list(request):
    """公告列表：置顶优先 + 未读标记 + 已读人数。"""
    read_ids = AnnouncementRead.objects.filter(
        user=request.user).values_list('announcement_id', flat=True)
    announcements = Announcement.objects.annotate(read_count=Count('read_records'))
    return render(request, 'notice/notice_list.html', {
        'announcements': announcements,
        'read_ids': set(read_ids),
    })


@login_required
def notice_detail(request, pk):
    """公告详情：访问即记已读（幂等）。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    AnnouncementRead.objects.get_or_create(
        announcement=announcement, user=request.user)
    return render(request, 'notice/notice_detail.html', {
        'announcement': announcement,
        'read_count': announcement.read_records.count(),
    })


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
            return redirect('notice:notice_list')
    return render(request, 'notice/notice_form.html')
