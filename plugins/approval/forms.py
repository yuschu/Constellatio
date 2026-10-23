"""approval 插件动态表单（v1.5.5，v1.5.14 调整报销金额与用章附件）。

按审批类型渲染对应输入项：
- 请假：请假时间* / 事由 / 部门* / 审批人（可留空）
- 报销：提交时间* / **金额*** / 费用事由 / 部门* / 审批人
- 用章：申请用章时间* / **用章文件*（上传）** / 用途 / 部门* / 审批人
- 外出：外出起止时间* / 外出事由 / 部门* / 审批人
- 加班：加班起止时间* / 加班事由 / 部门* / 审批人
- 调休：调休起止时间* / 调休依据*（关联加班记录） / 部门* / 审批人
"""

from decimal import Decimal

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from .models import Approval

TEXT = {'class': 'r-input'}
DATETIME = {'type': 'datetime-local', 'class': 'r-input'}
DATE = {'type': 'date', 'class': 'r-input'}

# v1.5.14：用章附件限制（单文件 10MB；常见文档 / 图片）
MAX_ATTACHMENT_MB = 10
ATTACHMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg']


def _required(widget, label):
    return forms.CharField(label=label, required=True, widget=widget)


class BaseApprovalForm(forms.Form):
    """公共字段：部门*、审批人*（v1.5.18：限定相关业务负责人，去掉留空）。"""

    department = forms.ChoiceField(label=_('部门'), required=True, widget=forms.Select(attrs=TEXT))
    approver = forms.ChoiceField(label=_('审批人'), required=True, widget=forms.Select(attrs=TEXT))

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

        # v1.5.18：审批人只列相关业务负责人（管辖部门经理 / 审批负责人），不留空选项
        approver_choices = [
            (str(user.pk), f'{user.last_name or user.username}（{user.username}）')
            for user in approvers or []
        ]
        self.fields['approver'].choices = approver_choices
        if approver_choices:
            self.fields['approver'].initial = approver_choices[0][0]

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
    # v1.5.14：报销金额必填
    amount = forms.DecimalField(
        label=_('金额'), required=True, max_digits=12, decimal_places=2,
        min_value=Decimal('0'),
        widget=forms.NumberInput(attrs={**TEXT, 'step': '0.01', 'min': '0'}))
    reason = forms.CharField(label=_('费用事由'), required=False,
                             widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))


class SealForm(BaseApprovalForm):
    seal_time = _required(forms.DateTimeInput(attrs=DATETIME), _('申请用章时间'))
    # v1.5.14：用章文件（附件，必填）+ 用途拆分
    seal_file = forms.FileField(
        label=_('用章文件'), required=True,
        widget=forms.ClearableFileInput(attrs={
            'class': 'r-input',
            'accept': ','.join(f'.{ext}' for ext in ATTACHMENT_EXTENSIONS),
        }),
        validators=[FileExtensionValidator(ATTACHMENT_EXTENSIONS)])
    purpose = forms.CharField(label=_('用途'), required=False,
                              widget=forms.Textarea(attrs={**TEXT, 'rows': 3}))

    def clean_seal_file(self):
        upload = self.cleaned_data.get('seal_file')
        if upload and upload.size > MAX_ATTACHMENT_MB * 1024 * 1024:
            raise forms.ValidationError(
                _('文件不能超过 %(mb)sMB') % {'mb': MAX_ATTACHMENT_MB})
        return upload


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
    # v1.5.15：调休改为时间段（结束必须晚于开始，由 BaseApprovalForm.clean 校验）
    start_time = _required(forms.DateTimeInput(attrs=DATETIME), _('调休开始时间'))
    end_time = _required(forms.DateTimeInput(attrs=DATETIME), _('调休结束时间'))
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
    Approval.Type.EXPENSE: ('submit_time', 'amount', 'reason'),
    Approval.Type.SEAL: ('seal_time', 'seal_file', 'purpose'),
    Approval.Type.OUTING: ('start_time', 'end_time', 'reason'),
    Approval.Type.OVERTIME: ('start_time', 'end_time', 'reason'),
    Approval.Type.COMP: ('start_time', 'end_time', 'basis'),
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
