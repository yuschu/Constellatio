"""blockchain 插件视图：留痕列表 + 链完整性校验 + 统计看板（v1.6.1）。"""

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Max
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from plugin_host.charts import get_active_chart
from plugin_host.pagination import paginate
from plugin_host.permissions import require_perm
from plugin_host.registry import PLUGIN_REGISTRY

from .models import BlockchainRecord

DEFAULT_STATS_DAYS = 30
MAX_STATS_DAYS = 90

# v1.7.1（P1-21）：链校验快照缓存秒数。
# 列表与详情每次都全表重算，记录增长后是 O(n) 的固定开销；缓存后同一链状态
# 在窗口内只算一次。缓存键含 (max_id, count)，追加新记录会自动换键；
# 原地篡改（直接 UPDATE 改 payload_hash）最多延迟本窗口被发现 —— 需要即时
# 结论时用 _verify_snapshot(force=True)（手动校验入口）。
VERIFY_CACHE_SECONDS = 60


def _verify_snapshot(force=False):
    """返回 (ok, broken_id)：默认走 60 秒缓存，force=True 时全量重算。"""
    if force:
        return BlockchainRecord.verify_chain()
    head = BlockchainRecord.objects.aggregate(max_id=Max('id'), total=Count('id'))
    cache_key = f'blockchain:verify:{head["max_id"] or 0}:{head["total"]}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = BlockchainRecord.verify_chain()
    cache.set(cache_key, result, VERIFY_CACHE_SECONDS)
    return result



def _parse_days(raw):
    """?days= 解析：空 → 默认 30；非整数或越界抛 ValueError。"""
    if raw in (None, ''):
        return DEFAULT_STATS_DAYS
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise ValueError('invalid days') from None
    if not 1 <= days <= MAX_STATS_DAYS:
        raise ValueError('invalid days')
    return days


def _plugin_label(key):
    """来源插件展示名：注册表 title（已本地化），未知 key 原样输出。"""
    meta = PLUGIN_REGISTRY.get(key)
    return str(meta.title) if meta else key


def _window_stats(days):
    """按日 × 来源插件聚合留痕（窗口 = 含今天的最近 N 天）。

    返回 (stats, table)：
    - stats 是 /stats/ 的 JSON 契约（见 docs/plugin-dev-v161.md §2.2）；
    - table 是服务端降级表格数据（labels / rows / totals / records）。
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    records = BlockchainRecord.objects.filter(created_at__date__range=(start, today))
    per_day = {
        (row['day'], row['plugin']): row['n']
        for row in records.annotate(day=TruncDate('created_at'))
                          .values('day', 'plugin').annotate(n=Count('id'))
    }

    plugin_totals = {}
    for (_day, plugin), count in per_day.items():
        plugin_totals[plugin] = plugin_totals.get(plugin, 0) + count
    ordered = sorted(plugin_totals, key=lambda key: (-plugin_totals[key], key))

    day_list = [start + timedelta(days=offset) for offset in range(days)]
    series = [{
        'key': key,
        'label': _plugin_label(key),
        'data': [per_day.get((day, key), 0) for day in day_list],
    } for key in ordered]

    table_rows = []
    for index, day in enumerate(day_list):
        cells = [item['data'][index] for item in series]
        total = sum(cells)
        if total:
            table_rows.append({'date': day.strftime('%m-%d'), 'cells': cells, 'total': total})

    stats = {
        'days': days,
        'range': {'start': start.isoformat(), 'end': today.isoformat()},
        'dates': [day.strftime('%m-%d') for day in day_list],
        'series': series,
        'totals': {'records': sum(plugin_totals.values())},
    }
    table = {
        'labels': [item['label'] for item in series],
        'rows': table_rows,
        'totals': [sum(item['data']) for item in series],
        'records': stats['totals']['records'],
        'colspan': len(series) + 2,
    }
    return stats, table


BLOCKCHAIN_PAGE_SIZE = 50


def _stats_snapshot(days=DEFAULT_STATS_DAYS):
    """看板 60 秒快照（v1.7.6）：翻页不再重复聚合，也不会出现「直接访问第 2 页看板空」。

    与 `_verify_snapshot` 同一套路：键含天数与当天日期，跨天自动换键。
    每次请求多 1 次 cache.get（DatabaseCache 一次 SELECT），省掉 2 次聚合查询。
    """
    key = f'blockchain:stats:{days}:{timezone.localdate()}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _window_stats(days)
    cache.set(key, result, 60)
    return result


@require_perm('blockchain_view')
def blockchain_list(request):
    """活动记录列表（倒序，50/页） + 校验结果 + 近 30 天统计看板。

    v1.7.6：原来硬切 [:100]，第 100 条以前的记录 UI 上不可达；改为分页并保留总数，
    看板走 60 秒快照（每页都渲染，不会出现「直接打开第 2 页看板是空的」）。
    """
    records = BlockchainRecord.objects.select_related('operator').order_by('-id')
    page_obj = paginate(request, records, BLOCKCHAIN_PAGE_SIZE)
    ok, broken_id = _verify_snapshot()
    _stats, table = _stats_snapshot(DEFAULT_STATS_DAYS)
    return render(request, 'blockchain/blockchain_list.html', {
        'records': page_obj,
        'page_obj': page_obj,
        'verify_ok': ok,
        'broken_id': broken_id,
        'total': page_obj.paginator.count,
        'chart': get_active_chart(),
        'chart_days': DEFAULT_STATS_DAYS,
        'chart_labels': table['labels'],
        'chart_rows': table['rows'],
        'chart_totals': table['totals'],
        'chart_records': table['records'],
        'chart_colspan': table['colspan'],
    })


@require_perm('blockchain_view')
def blockchain_stats(request):
    """活动统计 JSON（v1.6.1）：按日 × 来源插件；图表停用时 payload=null。"""
    try:
        days = _parse_days(request.GET.get('days'))
    except ValueError:
        return JsonResponse({
            # v1.7.5：JSON 错误体统一为 {code, message}
            'code': 'invalid_days',
            'message': _('时间窗口应为 1–90 天'),
        }, status=400)

    stats, _table = _window_stats(days)
    chart = get_active_chart()
    if chart is None:
        stats['payload'] = None
    else:
        stats['payload'] = chart.payload(
            categories=stats['dates'],
            series=[{'key': item['key'], 'name': item['label'], 'data': item['data']}
                    for item in stats['series']],
        )
    return JsonResponse(stats)


@require_perm('blockchain_view')
def blockchain_detail(request, record_id):
    """单条留痕详情：字段 + 链校验状态。"""
    record = get_object_or_404(
        BlockchainRecord.objects.select_related('operator'), pk=record_id)
    ok, broken_id = _verify_snapshot()
    return render(request, 'blockchain/blockchain_detail.html', {
        'record': record,
        'verify_ok': ok,
        'broken_id': broken_id,
        'back_url': reverse('blockchain:blockchain_list'),
    })
