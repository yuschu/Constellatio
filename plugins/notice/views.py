"""notice 插件视图：公告流 / 自动已读 / 已读人员 / 发布（v1.6.11）。"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from plugin_host.permissions import require_perm
from plugin_host.signals import notice_published

from .models import Announcement, AnnouncementRead


@login_required
def notice_list(request):
    """公告中心：单列公告流，一次展示全部公告并自动登记当前用户已读。"""
    announcement_ids = list(Announcement.objects.values_list('pk', flat=True))
    AnnouncementRead.objects.bulk_create(
        [AnnouncementRead(announcement_id=pk, user=request.user)
         for pk in announcement_ids],
        ignore_conflicts=True,
    )
    announcements = list(
        Announcement.objects.annotate(read_count=Count('read_records'))
        .order_by('-is_top', '-created_at'))
    return render(request, 'notice/notice_list.html', {
        'announcements': announcements,
    })


@require_perm('notice_manage')
def notice_readers(request, pk):
    """公告已读人员明细（仅 notice_manage 可见）。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    readers = list(
        AnnouncementRead.objects.filter(announcement=announcement)
        .select_related('user').order_by('-read_at'))
    return render(request, 'notice/notice_list.html', {
        'readers_view': announcement,
        'readers': readers,
    })


@login_required
def notice_detail(request, pk):
    """兼容旧详情链接：302 到列表页对应锚点，不再渲染独立详情页。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    return redirect(f"{reverse('notice:notice_list')}#notice-{announcement.pk}")


@require_perm('notice_manage')
def notice_create(request):
    """发布公告（需 notice_manage 权限），发布即发信号。"""
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
