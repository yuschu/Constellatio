"""user 插件表单：部门 / 用户 / 角色 / 个人资料 / 修改密码。"""

from django import forms
from django.contrib.auth.models import Permission
from django.utils.translation import get_language, gettext_lazy as _

from .models import Department, Role, User

DEFAULT_PASSWORD = 'constellatio123'


class PermissionMultipleChoice(forms.ModelMultipleChoiceField):
    """权限多选：中文显示 Permission.name，英文显示 app | codename，避免权限元数据中文残留。"""

    def label_from_instance(self, obj):
        if (get_language() or '').startswith('en'):
            return f'{obj.content_type.app_label} | {obj.codename}'
        return obj.name


def grantable_permissions(operator, target=None):
    """当前操作者可授予的权限；保留目标已有权限，避免编辑时被静默清空。"""
    if operator is None or operator.is_superuser:
        qs = Permission.objects.all()
    else:
        ids = set(operator.user_permissions.values_list('pk', flat=True))
        for role in operator.roles.all():
            ids.update(role.permissions.values_list('pk', flat=True))
        qs = Permission.objects.filter(pk__in=ids)
    if target is not None and getattr(target, 'pk', None):
        existing = set(target.user_permissions.values_list('pk', flat=True))
        qs = Permission.objects.filter(pk__in=set(qs.values_list('pk', flat=True)) | existing)
    return qs


def grantable_roles(operator, target=None):
    """当前操作者可授予的角色；只显示权限集合不超过操作者自身的角色。"""
    if operator is None or operator.is_superuser:
        qs = Role.objects.all()
    else:
        allowed = set(grantable_permissions(operator).values_list('pk', flat=True))
        ids = []
        for role in Role.objects.prefetch_related('permissions'):
            if set(role.permissions.values_list('pk', flat=True)) <= allowed:
                ids.append(role.pk)
        qs = Role.objects.filter(pk__in=ids)
    if target is not None and getattr(target, 'pk', None):
        existing = set(target.roles.values_list('pk', flat=True))
        qs = Role.objects.filter(pk__in=set(qs.values_list('pk', flat=True)) | existing)
    return qs


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'parent']
        widgets = {'name': forms.TextInput(attrs={'class': 'r-input', 'placeholder': _('部门名称')})}


class UserForm(forms.ModelForm):
    """用户创建/编辑：初始密码仅新建时生效；权限/角色只展示操作者可授予的范围。"""

    password = forms.CharField(
        required=False, widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}),
        label=_('初始密码（留空使用默认）'))
    password_confirm = forms.CharField(
        required=False, widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}),
        label=_('确认密码'))
    user_permissions = PermissionMultipleChoice(
        queryset=Permission.objects.none(),
        required=False,
        label=_('直接权限（额外）'),
        help_text=_('只能授予你自身拥有的权限'),
        widget=forms.SelectMultiple(attrs={'size': '12', 'class': 'r-input'}),
    )

    class Meta:
        model = User
        fields = ['username', 'last_name', 'email', 'department', 'roles',
                  'user_permissions', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'r-input'}),
            'last_name': forms.TextInput(attrs={'class': 'r-input'}),
            'email': forms.EmailInput(attrs={'class': 'r-input'}),
            'roles': forms.SelectMultiple(attrs={'size': '12', 'class': 'r-input'}),
            'is_active': forms.CheckboxInput(),
        }

    def __init__(self, *args, operator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user_permissions'].queryset = grantable_permissions(operator, self.instance)
        self.fields['roles'].queryset = grantable_roles(operator, self.instance)

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


class ProfileForm(forms.ModelForm):
    """个人中心资料编辑：只允许改姓名和邮箱，禁止改角色/权限/状态。"""

    class Meta:
        model = User
        fields = ['last_name', 'email']
        widgets = {
            'last_name': forms.TextInput(attrs={'class': 'r-input'}),
            'email': forms.EmailInput(attrs={'class': 'r-input'}),
        }


class PasswordForm(forms.Form):
    old_password = forms.CharField(
        label=_('当前密码'),
        widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'current-password'}))
    new_password = forms.CharField(
        label=_('新密码'),
        widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}))
    confirm_password = forms.CharField(
        label=_('确认新密码'),
        widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}))

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        pwd = self.cleaned_data.get('old_password')
        if not self.user or not self.user.check_password(pwd):
            raise forms.ValidationError(_('当前密码错误'))
        return pwd

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get('new_password')
        confirm = cleaned.get('confirm_password')
        if new and confirm and new != confirm:
            raise forms.ValidationError(_('两次输入的新密码不一致'))
        return cleaned


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
