"""助手消息的轻量文本渲染：先转义，再还原少量安全标记。"""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_BOLD = re.compile(r'\*\*(.+?)\*\*', re.S)
_CODE = re.compile(r'`(.+?)`', re.S)


@register.filter
def chat_text(value):
    """把 `**粗体**`、`` `代码` `` 和换行转成安全 HTML，其余字符原样转义。"""
    text = escape(value or '')
    text = _BOLD.sub(r'<strong>\1</strong>', text)
    text = _CODE.sub(r'<code>\1</code>', text)
    return mark_safe(text.replace('\n', '<br>'))
