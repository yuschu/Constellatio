"""助手模型配置表单（A 阶段）。

只做输入清洗，不写库；保存与探测在视图里完成。`api_key` 永远不回显，
留空表示沿用当前值，勾选“清除”才会删掉。
"""

from urllib.parse import urlparse

from django import forms
from django.utils.translation import gettext_lazy as _


class LLMSettingsForm(forms.Form):
    base_url = forms.CharField(
        label=_('接口地址'), max_length=300, required=False,
        help_text=_('OpenAI 兼容根地址，例如 http://127.0.0.1:11434/v1'))
    model = forms.CharField(
        label=_('模型名'), max_length=120, required=False,
        help_text=_('服务端实际加载的模型名，例如 qwen3:4b'))
    api_key = forms.CharField(
        label=_('API Key'), max_length=500, required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=_('本地 ollama / llama.cpp 通常不需要；留空保持不变'))
    clear_api_key = forms.BooleanField(label=_('清除已保存的 API Key'), required=False)
    timeout_seconds = forms.IntegerField(
        label=_('超时（秒）'), min_value=1, max_value=120, initial=30,
        help_text=_('单次模型请求的最长等待时间，1–120 秒'))
    max_tokens = forms.IntegerField(
        label=_('输出上限'), min_value=1, max_value=8192, initial=1024,
        help_text=_('单次回复的最大 token 数，1–8192'))

    def clean_base_url(self):
        value = (self.cleaned_data.get('base_url') or '').strip().rstrip('/')
        if not value:
            return ''
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise forms.ValidationError(_('接口地址必须是 http:// 或 https:// 开头的完整地址'))
        if parsed.username or parsed.password:
            raise forms.ValidationError(_('接口地址不能包含用户名或密码'))
        if parsed.query or parsed.fragment:
            raise forms.ValidationError(_('接口地址不能带查询参数或锚点'))
        return value

    def clean_model(self):
        return (self.cleaned_data.get('model') or '').strip()

    def clean(self):
        cleaned = super().clean()
        base_url = cleaned.get('base_url')
        model = cleaned.get('model')
        if base_url and not model:
            self.add_error('model', _('填了接口地址就必须填模型名'))
        if model and not base_url:
            self.add_error('base_url', _('填了模型名就必须填接口地址'))
        return cleaned
