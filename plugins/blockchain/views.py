"""blockchain 插件视图：留痕列表 + 链完整性校验。"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import BlockchainRecord


@login_required
def blockchain_list(request):
    """留痕链列表（倒序） + 校验结果。"""
    records = BlockchainRecord.objects.select_related('operator')[:100]
    ok, broken_id = BlockchainRecord.verify_chain()
    return render(request, 'blockchain/blockchain_list.html', {
        'records': records,
        'verify_ok': ok,
        'broken_id': broken_id,
        'total': BlockchainRecord.objects.count(),
    })


@login_required
def blockchain_detail(request, record_id):
    """单条留痕详情：字段 + 链校验状态。"""
    record = get_object_or_404(
        BlockchainRecord.objects.select_related('operator'), pk=record_id)
    ok, broken_id = BlockchainRecord.verify_chain()
    return render(request, 'blockchain/blockchain_detail.html', {
        'record': record,
        'verify_ok': ok,
        'broken_id': broken_id,
    })
