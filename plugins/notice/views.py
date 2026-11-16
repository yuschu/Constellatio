"""notice 插件视图：公告流 / 自动已读 / 已读人员 / 发布（v1.6.11）。"""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from plugin_host.pagination import paginate
from plugin_host.permissions import require_perm
from plugin_host.signals import notice_published

from .models import Announcement, AnnouncementRead
from .services import attachment_name, validate_attachment


@login_required
def notice_list(request):
    """公告：单列公告流，分页展示，并只登记**当页**里当前用户未读的公告。

    v1.7.6：原实现每次进来都取全部公告 id 再全量 bulk_create，写入量与公告总量线性相关；
    改为「当页 → 已读集合 → 差集登记」。保留 `ignore_conflicts=True` 兜并发：
    两个请求同时判定未读时会各自 insert，由 `unique_together` 去重，不产生重复行。
    v2.1.3：列表与「发布公告」设置弹层共用 _render_notice_list 一次渲染。
    """
    # 弹层里的表单 action 为空 → POST 回到本页，这里分派给 notice_create，
    # 校验失败由 notice_create 渲染回列表弹层（错误就地显示）。
    if request.method == 'POST':
        return notice_create(request)
    return _render_notice_list(request, form_open=request.GET.get('view') == 'new')


def notice_list_context(
        request, *, form_data=None, form_open=False, readers=None,
        form_error='', panel=False):
    """公告列表上下文：业务页与首页 `?panel=notice` 面板共用。

    v2.4.1：列表正文抽成同一份上下文 / partial。`panel=True` 时所有站内链接
    回到 `/?panel=notice`，分页链接带 `data-panel-link`，由首页只换正文。

    v2.1.3：发布公告改 DSH 设置弹层形态（单分区 → 不渲染左侧 188px 分区列，
    内容与按钮居中）。`?view=new` 或标题/正文为空时 form_open=True，列表与
    弹层一次渲染完，并把已填内容回填（原来非法 POST 直接丢字重画）。

    「已读人员」也不再是另一套页面：`readers` 传入某条公告时，同一个列表
    把名单渲染进设置弹层（`notice_readers` 视图就是这么用的）。
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

    if panel:
        list_url = f'{reverse("index")}?panel=notice'
        create_url = f'{list_url}&view=new'
    else:
        list_url = reverse('notice:notice_list')
        create_url = f'{list_url}?view=new'

    readers_ctx = {}
    if readers is not None:
        readers_ctx = {
            'readers_view': readers,
            'readers': list(
                AnnouncementRead.objects.filter(announcement=readers)
                .select_related('user').order_by('-read_at')),
            'readers_open': True,
            'readers_url': reverse('notice:notice_readers', args=[readers.pk]),
        }
    can_manage_notice = request.user.has_perm('notice_manage')
    return {
        'announcements': page_obj,
        'page_obj': page_obj,
        'notice_create_url': create_url if can_manage_notice else '',
        'notice_list_url': list_url,
        'notice_form_open': form_open,
        'form_data': form_data or {},
        'form_error': form_error,
        'panel_links': panel,
        **readers_ctx,
    }


def _render_notice_list(request, form_data=None, form_open=False, readers=None, form_error=''):
    """公告业务页的唯一渲染入口（列表 + 发布 / 已读人员两个设置弹层）。"""
    return render(request, 'notice/notice_list.html', notice_list_context(
        request, form_data=form_data, form_open=form_open,
        readers=readers, form_error=form_error))


@require_perm('notice_manage')
def notice_readers(request, pk):
    """公告已读人员明细（仅 notice_manage 可见）：同一张列表页 + 设置弹层。

    不再复制一套「已读人员」页面：明细塞进公告列表的设置弹层里，
    地址仍是本页，弹层默认打开（`data-ds-subpage-url` 指向本页）。
    """
    announcement = get_object_or_404(Announcement, pk=pk)
    return _render_notice_list(request, readers=announcement)


@login_required
def notice_detail(request, pk):
    """兼容旧详情链接：302 到列表页对应锚点，不再渲染独立详情页。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    return redirect(f"{reverse('notice:notice_list')}#notice-{announcement.pk}")


def create_announcement_from_post(request):
    """从 POST 校验并创建公告，供业务页与首页面板共用。

    返回 `(announcement, error, form_data)`：成功时 announcement 有值，
    失败时 error 为非空字符串、form_data 用于回填弹层。信号只在真正落库后
    发一次，避免首页和业务页各写一套发布逻辑。
    """
    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '')
    uploaded = request.FILES.get('attachment')
    form_data = {
        'title': title,
        'content': content,
        'is_top': request.POST.get('is_top') == 'on',
        'attachment_name': attachment_name_from_upload(uploaded),
    }
    if not title or not content:
        return None, '标题和正文不能为空', form_data
    attachment_error = validate_attachment(uploaded)
    if attachment_error:
        return None, attachment_error, form_data

    with transaction.atomic():
        announcement = Announcement.objects.create(
            title=title, content=content, publisher=request.user,
            is_top=request.POST.get('is_top') == 'on',
            attachment=uploaded)
    notice_published.send(
        sender=announcement.__class__, announcement_id=announcement.id)
    return announcement, '', form_data


@require_perm('notice_manage')
def notice_create(request):
    """发布公告（需 notice_manage 权限），发布即发信号。

    v2.1.3：GET 渲染设置面板深链页；POST 校验失败回到公告业务页并把已填内容
    回填到弹层里（form_open=True）。
    v2.4.0：支持单附件上传（类型/大小沿用审批附件口径），附件随公告保存。
    v2.4.1：发布逻辑抽到 create_announcement_from_post()，首页 `?panel=notice`
    面板直接复用，成功/失败都回首页面板。
    """
    if request.method == 'POST':
        announcement, error, form_data = create_announcement_from_post(request)
        if announcement is not None:
            return redirect('notice:notice_list')
        return _render_notice_list(
            request, form_data, form_open=True, form_error=error)
    return render(request, 'notice/notice_form.html', {
        'back_url': reverse('notice:notice_list'),
        'form_data': {},
    })


def attachment_name_from_upload(uploaded):
    """校验失败时只回显原始文件名，不回显内容，也不落盘。"""
    import os
    return os.path.basename(getattr(uploaded, 'name', '') or '') if uploaded else ''


@login_required
def notice_attachment(request, pk):
    """公告附件下载：与公告流同一可见范围（登录即可看，不额外要求 notice_view）。

    这里只做对象存在性与附件存在性校验，不暴露 media 直链，也不返回目录列表。
    """
    announcement = get_object_or_404(Announcement, pk=pk)
    if not announcement.attachment:
        return HttpResponseNotFound('公告没有附件')
    name = attachment_name(announcement)
    response = FileResponse(
        announcement.attachment.open('rb'), as_attachment=True, filename=name)
    response['X-Content-Type-Options'] = 'nosniff'
    return response
