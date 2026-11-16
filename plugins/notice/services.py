"""notice 附件校验：类型与大小沿用审批附件口径，单附件、10MB。"""

from __future__ import annotations

import os

from django.utils.translation import gettext as _

MAX_ATTACHMENT_MB = 10
ATTACHMENT_EXTENSIONS = (
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'zip', 'png', 'jpg', 'jpeg',
)
MAX_ATTACHMENT_BYTES = MAX_ATTACHMENT_MB * 1024 * 1024


def validate_attachment(uploaded) -> str | None:
    """返回错误文案；通过返回 None。空文件也视为错误。"""
    if uploaded is None:
        return None
    name = os.path.basename(getattr(uploaded, 'name', '') or '')
    if not name:
        return _('请选择要上传的文件')
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in ATTACHMENT_EXTENSIONS:
        return _('不支持该文件类型，仅支持 PDF / Office / 图片 / TXT / CSV / ZIP')
    if getattr(uploaded, 'size', 0) > MAX_ATTACHMENT_BYTES:
        return _('附件不能超过 %(mb)sMB') % {'mb': MAX_ATTACHMENT_MB}
    if getattr(uploaded, 'size', 0) <= 0:
        return _('附件为空，请重新选择')
    return None


def attachment_name(announcement) -> str:
    if not announcement.attachment:
        return ''
    return os.path.basename(announcement.attachment.name)


def format_size(size: int | None) -> str:
    size = size or 0
    if size < 1024:
        return f'{size} B'
    if size < 1024 * 1024:
        return f'{size / 1024:.0f} KB'
    return f'{size / (1024 * 1024):.1f} MB'
