"""attendance 插件表单：考勤规则（单例）。"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import AttendanceRule

INPUT = {'class': 'r-input'}
TIME_INPUT = {'type': 'time', 'class': 'r-input'}
NUMBER_INPUT = {'type': 'number', 'class': 'r-input', 'min': '0', 'max': '120'}

# 表单校验边界（与任务口径一致）
GRACE_MIN, GRACE_MAX = 0, 120
MAKEUP_MIN, MAKEUP_MAX = 1, 90


class AttendanceRuleForm(forms.ModelForm):
    """考勤规则表单：上下班时间 / 宽限 / 工作日 / 补卡回溯。"""

    class Meta:
        model = AttendanceRule
        fields = [
            'work_start', 'work_end',
            'late_grace_minutes', 'early_grace_minutes',
            'workdays', 'makeup_window_days',
        ]
        widgets = {
            'work_start': forms.TimeInput(attrs=TIME_INPUT, format='%H:%M'),
            'work_end': forms.TimeInput(attrs=TIME_INPUT, format='%H:%M'),
            'late_grace_minutes': forms.NumberInput(attrs=NUMBER_INPUT),
            'early_grace_minutes': forms.NumberInput(attrs=NUMBER_INPUT),
            'workdays': forms.TextInput(attrs={
                **INPUT, 'placeholder': '1,2,3,4,5'}),
            'makeup_window_days': forms.NumberInput(attrs={
                **INPUT, 'min': '1', 'max': '90'}),
        }

    def clean_late_grace_minutes(self):
        value = self.cleaned_data.get('late_grace_minutes')
        if value is not None and not GRACE_MIN <= value <= GRACE_MAX:
            raise forms.ValidationError(
                _('迟到宽限须在 0–120 分钟之间'))
        return value

    def clean_early_grace_minutes(self):
        value = self.cleaned_data.get('early_grace_minutes')
        if value is not None and not GRACE_MIN <= value <= GRACE_MAX:
            raise forms.ValidationError(
                _('早退宽限须在 0–120 分钟之间'))
        return value

    def clean_workdays(self):
        raw = (self.cleaned_data.get('workdays') or '').strip()
        days = set()
        for part in raw.split(','):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                raise forms.ValidationError(
                    _('工作日须为 1–7 的逗号分隔数字，例如 1,2,3,4,5'))
            day = int(part)
            if not 1 <= day <= 7:
                raise forms.ValidationError(
                    _('工作日取值范围为 1–7（1=周一，7=周日）'))
            days.add(day)
        if not days:
            raise forms.ValidationError(_('请至少选择一个工作日'))
        return ','.join(str(day) for day in sorted(days))

    def clean_makeup_window_days(self):
        value = self.cleaned_data.get('makeup_window_days')
        if value is not None and not MAKEUP_MIN <= value <= MAKEUP_MAX:
            raise forms.ValidationError(
                _('补卡回溯天数须在 1–90 天之间'))
        return value

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('work_start')
        end = cleaned.get('work_end')
        if start and end and start >= end:
            self.add_error('work_end', _('下班时间必须晚于上班时间'))
        return cleaned
