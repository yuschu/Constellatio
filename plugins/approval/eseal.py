"""电子章服务接口（v1.5.15 占位实现）。

真实电子章插件接入点：调用 ``apply_e_seal(approval)``，返回盖章结果文本
（后续可扩展为图片 / PDF 回写）。当前为占位：只写入 form_data['e_seal'] 文本，
不改变审批状态、不产生外部副作用。
"""

PLACEHOLDER_TEXT = '电子盖章（占位）：电子章插件尚未接入，审批通过后待插件上线自动盖章。'


def apply_e_seal(approval):
    """对用章审批执行（占位）电子盖章，返回展示文本。"""
    approval.form_data['e_seal'] = {
        'status': 'placeholder',
        'text': PLACEHOLDER_TEXT,
    }
    approval.save(update_fields=['form_data', 'updated_at'])
    return PLACEHOLDER_TEXT
