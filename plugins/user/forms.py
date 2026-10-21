"""user 插件表单：部门 / 用户 / 角色。

v1.2：密码二次确认（password_confirm）；部门表单复用编辑。
"""

from django import forms

from .models import Department, Role, User

DEFAULT_PASSWORD = 'constellatio123'


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'parent']
        widgets = {'name': forms.TextInput(attrs={'class': 'r-input', 'placeholder': '部门名称'})}


class UserForm(forms.ModelForm):
    """用户创建/编辑：初始密码仅新建时生效（留空用默认密码）；二次确认必填一致。"""

    password = forms.CharField(
        required=False, widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}),
        label='初始密码（留空使用默认）')
    password_confirm = forms.CharField(
        required=False, widget=forms.PasswordInput(attrs={'class': 'r-input', 'autocomplete': 'new-password'}),
        label='确认密码')

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
            raise forms.ValidationError('两次输入的密码不一致')
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


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ['name', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'r-input'}),
            'permissions': forms.SelectMultiple(attrs={'size': '12', 'class': 'r-input'}),
        }
