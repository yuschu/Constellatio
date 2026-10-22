"""approval 插件动态表单（v1.5.5）。

按审批类型渲染对应输入项：
- 请假：请假时间* / 事由 / 部门* / 审批人（可留空）
- 报销：提交时间* / 费用事由 / 部门* / 审批人
- 用章：申请用章时间* / 用章文件及用途 / 部门* / 审批人
- 外出：外出起止时间* / 外出事由 / 部门* / 审批人
- 加班：加班起止时间* / 加班事由 / 部门* / 审批人
- 调休：调休时间* / 调休依据*（关联加班记录） / 部门* / 审批人
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Approval

TEXT = {'class': 'r-input'}
DATETIME = {'type': 'datetime-local', 'class': 'r-input'}
DATE = {'type': 'date', 'class': 'r-input'}


def _required(widget, label):
    return forms.CharField(label=label, required=True, widget=widget)


class BaseApprovalForm(forms.Form):
    """公共字段：部门*、审批人（可留空 → 直属上级 → 兜底管理员）。"""

    department = forms.ChoiceField(label=_('部门'), required=True, widget=forms.Select(attrs=TEXT))
    approver = forms.ChoiceField(label=_('审批人'), required=False, widget=forms.Select(attrs=TEXT))

    def __init__(self, *args, applicant=None, departments=None, approvers=None,
                 overtime_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.applicant = applicant
        department_choices = [('', _('请选择部门'))]
        for dept in departments or []:
            department_choices.append((str(dept.pk), dept.name))
        self.fields['department'].choices = department_choices
        if applicant is not None and applicant.department_id:
            self.fields['department'].initial = str(applicant.department_id)

        approver_choices = [('', _('留空：由直属上级审批'))]
        for user in approvers or []:
            approver_choices.append(
                (str(user.pk), f'{user.last_name or user.username}（{user.username}）'))
        self.fields['approver'].choices = approver_choices
        if applicant is not None and applicant.leader_id:
            self.fields['approver'].initial = str(applicant.leader_id)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        if start and end and end <= start:
            raise forms.ValidationError(_('结束时间必须晚于开始时间'))
        return cleaned


class LeaveForm(BaseApprovalForm):
    leave_time = _required(forms.DateTimeInput(attrs=DATETIME), _('请假时间'))
    reason = forms.CharField(label=_('事由'), required=False,
                             widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))


class ExpenseForm(BaseApprovalForm):
    submit_time = _required(forms.DateInput(attrs=DATE), _('提交时间'))
    reason = forms.CharField(label=_('费用事由'), required=False,
                             widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))


class SealForm(BaseApprovalForm):
    seal_time = _required(forms.DateTimeInput(attrs=DATETIME), _('申请用章时间'))
    document = forms.CharField(label=_('用章文件及用途'), required=False,
                               widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))


class OutingForm(BaseApprovalForm):
    start_time = _required(forms.DateTimeInput(attrs=DATETIME), _('外出开始时间'))
    end_time = _required(forms.DateTimeInput(attrs=DATETIME), _('外出结束时间'))
    reason = forms.CharField(label=_('外出事由'), required=False,
                             widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))


class OvertimeForm(BaseApprovalForm):
    start_time = _required(forms.DateTimeInput(attrs=DATETIME), _('加班开始时间'))
    end_time = _required(forms.DateTimeInput(attrs=DATETIME), _('加班结束时间'))
    reason = forms.CharField(label=_('加班事由'), required=False,
                             widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))


class CompForm(BaseApprovalForm):
    comp_time = _required(forms.DateTimeInput(attrs=DATETIME), _('调休时间'))
    basis = forms.ChoiceField(label=_('调休依据（关联加班记录）'), required=True,
                              widget=forms.Select(attrs=TEXT))

    def __init__(self, *args, overtime_choices=None, **kwargs):
        super().__init__(*args, overtime_choices=overtime_choices, **kwargs)
        choices = overtime_choices or []
        self.fields['basis'].choices = choices or [('', _('暂无加班记录'))]
        if not choices:
            self.fields['basis'].disabled = True

    def clean_basis(self):
        value = self.cleaned_data.get('basis')
        if not value:
            raise forms.ValidationError(_('请先发起并完成加班审批，再申请调休'))
        return value


FORM_CLASSES = {
    Approval.Type.LEAVE: LeaveForm,
    Approval.Type.EXPENSE: ExpenseForm,
    Approval.Type.SEAL: SealForm,
    Approval.Type.OUTING: OutingForm,
    Approval.Type.OVERTIME: OvertimeForm,
    Approval.Type.COMP: CompForm,
}

# 发起页面上的类型 Tab 顺序
FORM_TYPES = [
    Approval.Type.LEAVE, Approval.Type.EXPENSE, Approval.Type.SEAL,
    Approval.Type.OUTING, Approval.Type.OVERTIME, Approval.Type.COMP,
]

# 展示用：动态字段（不含部门/审批人）
_DISPLAY_FIELDS = {
    Approval.Type.LEAVE: ('leave_time', 'reason'),
    Approval.Type.EXPENSE: ('submit_time', 'reason'),
    Approval.Type.SEAL: ('seal_time', 'document'),
    Approval.Type.OUTING: ('start_time', 'end_time', 'reason'),
    Approval.Type.OVERTIME: ('start_time', 'end_time', 'reason'),
    Approval.Type.COMP: ('comp_time', 'basis'),
}


def form_for_type(approval_type, *args, **kwargs):
    """按类型返回表单实例；非法类型回退请假。"""
    form_class = FORM_CLASSES.get(approval_type, LeaveForm)
    return form_class(*args, **kwargs)


def type_fields(approval_type):
    """返回 [(field_name, label), ...]，用于详情展示。"""
    form = form_for_type(approval_type, departments=[], approvers=[])
    names = _DISPLAY_FIELDS.get(approval_type, ())
    return [(name, form.fields[name].label) for name in names if name in form.fields]
