"""列表分页（v1.7.6）：所有列表页共用一个入口，避免每个视图各写一份 `Paginator(...)`。

约定：
1. **先排序、再分页**。`Paginator` 只做 `LIMIT/OFFSET`，没有 `ORDER BY` 时 MySQL 的返回顺序
   不保证稳定，翻页会出现重复/漏行。传进来的 queryset 必须自带 `order_by(...)`
   （或用模型的 `Meta.ordering`，但要确认这条路径真的会生成 ORDER BY）。
2. `get_page()` 已经处理异常输入：非整数 → 第 1 页；越界（`EmptyPage`）→ **末页**。
   视图里不要自己 `try/except`，也不要手动算页号。
3. 页大小差异是有意的：普通列表 `DEFAULT_PAGE_SIZE`，留痕列表 50（审计表格更密）。
"""

from django.core.paginator import Paginator

DEFAULT_PAGE_SIZE = 25


def paginate(request, queryset, page_size=DEFAULT_PAGE_SIZE):
    """按 `?page=` 取一页；非法或越界由 `get_page()` 兜底成第 1 页 / 末页。"""
    return Paginator(queryset, page_size).get_page(request.GET.get('page'))
