"""notice 插件视图：公告流 / 自动已读 / 已读人员 / 发布（v1.6.11）。"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from plugin_host.pagination import paginate
from plugin_host.permissions import require_perm
from plugin_host.signals import notice_published

from .models import Announcement, AnnouncementRead


@login_required
def notice_list(request):
    """公告中心：单列公告流，分页展示，并只登记**当页**里当前用户未读的公告。

    v1.7.6：原实现每次进来都取全部公告 id 再全量 bulk_create，写入量与公告总量线性相关；
    改为「当页 → 已读集合 → 差集登记」。保留 `ignore_conflicts=True` 兜并发：
    两个请求同时判定未读时会各自 insert，由 `unique_together` 去重，不产生重复行。
    v2.1.3：列表与「发布公告」设置弹层共用 _render_notice_list 一次渲染。
    """
    return _render_notice_list(
        request, form_open=request.method == 'GET' and request.GET.get('view') == 'new')


def _render_notice_list(request, form_data=None, form_open=False):
    """公告中心的唯一渲染入口（列表 + 「发布公告」设置弹层）。

    v2.1.3：发布公告改 DSH 设置弹层形态（单分区 → 不渲染左侧 188px 分区列，
    内容与按钮居中）。`?view=new` 或标题/正文为空时 form_open=True，列表与
    弹层一次渲染完，并把已填内容回填（原来非法 POST 直接丢字重画）。
    """
    announcements = (
        Announcement.objects.annotate(read_count=Count('read_records'))
        .order_by('-is_top', '-created_at', '-id'))
    page_obj = paginate(request, announcements)
    page_ids = [item.pk for item in page_obj]
    if page_ids:
        read_ids = set(
            AnnouncementRead.objects
            .filter(user=request.user, announcement_id__in=page_ids)
            .values_list('announcement_id', flat=True))
        unread = [AnnouncementRead(announcement_id=pk, user=request.user)
                  for pk in page_ids if pk not in read_ids]
        if unread:
            AnnouncementRead.objects.bulk_create(unread, ignore_conflicts=True)
            fresh_ids = {row.announcement_id for row in unread}
            for item in page_obj:
                if item.pk in fresh_ids:
                    item.read_count += 1

    list_url = reverse('notice:notice_list')
    return render(request, 'notice/notice_list.html', {
        'announcements': page_obj,
        'page_obj': page_obj,
        'notice_create_url': f'{list_url}?view=new',
        'notice_list_url': list_url,
        'notice_form_open': form_open,
        'form_data': form_data or {},
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
    """发布公告（需 notice_manage 权限），发布即发信号。

    v2.1.3：GET 渲染设置面板深链页；POST 校验失败回到公告中心并把已填内容
    回填到弹层里（form_open=True）。
    """
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '')
        if title and content:
            announcement = Announcement.objects.create(
                title=title, content=content, publisher=request.user,
                is_top=request.POST.get('is_top') == 'on')
            notice_published.send(sender=announcement.__class__, announcement_id=announcement.id)
            return redirect('notice:notice_list')
        return _render_notice_list(request, {
            'title': title,
            'content': content,
            'is_top': request.POST.get('is_top') == 'on',
        }, form_open=True)
    return render(request, 'notice/notice_form.html', {
        'back_url': reverse('notice:notice_list'),
        'form_data': {},
    })
