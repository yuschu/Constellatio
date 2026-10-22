"""user 插件表单：部门 / 用户 / 角色。

v1.2：密码二次确认（password_confirm）；部门表单复用编辑。
"""

from django import forms
from django.contrib.auth.models import Permission
from django.utils.translation import get_language, gettext_lazy as _

from .models import Department, Role, User

DEFAULT_PASSWORD = 'constellatio123'


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'parent']
        widgets = {'name': forms.TextInput(attrs={'class': 'r-input', 'placeholder': _('部门名称')})}


class UserForm(forms.ModelForm):
    """用户创建/编辑：初始密码仅新建时生效（留空用默认密码）；二次确认必填一致。"""

    password = forms.CharField(
        required=False, widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}),
        label=_('初始密码（留空使用默认）'))
    password_confirm = forms.CharField(
        required=False, widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}),
        label=_('确认密码'))

    class Meta:
        model = User
        fields = ['username', 'last_name', 'email', 'department', 'roles', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'r-input'}),
            'last_name': forms.TextInput(attrs={'class': 'r-input'}),
            'email': forms.EmailInput(attrs={'class': 'r-input'}),
            'is_active': forms.CheckboxInput(),
        }

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get('password')
        confirm = cleaned.get('password_confirm')
        if pwd != confirm:
            raise forms.ValidationError(_('两次输入的密码不一致'))
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get('password')
        if pwd:
            user.set_password(pwd)
        elif not user.pk:
            user.set_password(DEFAULT_PASSWORD)
        if commit:
            user.save()
            self.save_m2m()
        return user


class PermissionMultipleChoice(forms.ModelMultipleChoiceField):
    """权限多选：中文显示 Permission.name，英文显示 app | codename，避免权限元数据中文残留。"""

    def label_from_instance(self, obj):
        if (get_language() or '').startswith('en'):
            return f'{obj.content_type.app_label} | {obj.codename}'
        return obj.name


class RoleForm(forms.ModelForm):
    permissions = PermissionMultipleChoice(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'size': '12', 'class': 'r-input'}),
    )

    class Meta:
        model = Role
        fields = ['name', 'permissions']
        widgets = {'name': forms.TextInput(attrs={'class': 'r-input'})}
