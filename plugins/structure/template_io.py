"""组织架构模板表：XLSX 生成 + 上传解析。

模板固定三张业务表（部门 / 角色 / 用户）和一张说明表。解析阶段只做全量校验，
不写库；任何一行不合法都返回错误清单，由视图决定不进入 apply_template，
因此失败时零写入。
"""

from __future__ import annotations

import io
import re
import zipfile

from django.apps import apps as dj_apps
from django.contrib.auth.models import Permission
from django.utils.translation import gettext as _
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from .template import (
    DEFAULT_PASSWORD,
    DEPARTMENTS,
    LEADER_OF,
    ROLE_PERMISSIONS,
    ROLES,
    USERS,
)

MAX_TEMPLATE_MB = 5
MAX_TEMPLATE_BYTES = MAX_TEMPLATE_MB * 1024 * 1024
SHEET_DEPARTMENTS = '部门'
SHEET_ROLES = '角色'
SHEET_USERS = '用户'
SHEET_HELP = '说明'

DEPT_HEADERS = {
    '部门名称': 'name', 'department': 'name', 'department name': 'name',
    '上级部门': 'parent', 'parent': 'parent', 'parent department': 'parent',
}
ROLE_HEADERS = {
    '角色名称': 'name', 'role': 'name', 'role name': 'name',
    '权限码': 'permissions', 'permission codes': 'permissions',
    'permissions': 'permissions', 'permission code': 'permissions',
}
USER_HEADERS = {
    '账号': 'account', 'username': 'account', 'account': 'account',
    '姓名': 'name', 'name': 'name',
    '部门': 'department', 'department': 'department',
    '角色': 'role', 'role': 'role',
    '直属上级账号': 'leader', 'leader username': 'leader', 'leader': 'leader',
}
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.@+-]+$')


class TemplateError(Exception):
    """模板校验失败：messages 为逐行可读错误。"""

    def __init__(self, messages):
        self.messages = list(messages)
        super().__init__('; '.join(self.messages))


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _split_codes(value) -> list[str]:
    return [part.strip() for part in re.split(r'[,，;；\n]+', _text(value)) if part.strip()]


def _header_key(value) -> str:
    text = _text(value).lstrip('\ufeff').strip().lower()
    for part in text.split('/'):
        part = part.strip()
        if part:
            return part
    return ''


def _map_headers(row, aliases):
    found = {}
    for index, value in enumerate(row):
        key = aliases.get(_header_key(value))
        if key and key not in found:
            found[key] = index
    return found


def _cell(row, index):
    if index is None or index >= len(row):
        return ''
    return _text(row[index])


def build_template_workbook() -> bytes:
    """生成内置架构模板；下载后可原样修改再上传。"""
    workbook = Workbook()
    workbook.remove(workbook.active)
    header_fill = PatternFill('solid', fgColor='F2F3F5')
    header_font = Font(name='Calibri', size=11, bold=True, color='1F2329')

    def add_sheet(title, headers, rows, widths):
        sheet = workbook.create_sheet(title)
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = 'A2'
        sheet.append(headers)
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical='center')
        sheet.row_dimensions[1].height = 24
        for row in rows:
            sheet.append(list(row))
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        return sheet

    add_sheet(
        SHEET_DEPARTMENTS,
        ['部门名称 / Department name', '上级部门 / Parent department'],
        [(name, parent or '') for name, parent in DEPARTMENTS],
        [34, 34])
    add_sheet(
        SHEET_ROLES,
        ['角色名称 / Role name', '权限码 / Permission codes'],
        [(name, ', '.join(sorted(ROLE_PERMISSIONS.get(name, set())))) for name in ROLES],
        [28, 78])
    add_sheet(
        SHEET_USERS,
        ['账号 / Username', '姓名 / Name', '部门 / Department',
         '角色 / Role', '直属上级账号 / Leader username'],
        [(account, name, dept, role, LEADER_OF.get(account) or '')
         for account, name, dept, role in USERS],
        [22, 18, 24, 22, 24])

    help_sheet = workbook.create_sheet(SHEET_HELP)
    help_sheet.sheet_view.showGridLines = False
    help_sheet.append(['组织架构模板导入说明 / Organization template instructions'])
    help_sheet['A1'].font = Font(name='Calibri', size=13, bold=True, color='1F2329')
    help_lines = [
        ('1', '只支持 .xlsx，文件不超过 5MB；三张业务表必须保留：部门 / 角色 / 用户。'),
        ('2', '空白行自动跳过；同一工作表内部门名、角色名、账号不能重复。'),
        ('3', '只创建缺失项，不覆盖既有部门、角色、用户；角色权限只增不减。'),
        ('4', '上级部门、角色、直属上级必须能在本表或现有架构中找到；部门层级不能成环。'),
        ('5', '新用户统一初始密码为 constellatio123；账号只允许字母、数字、_ . @ + -。'),
        ('6', '任一单元格校验失败则整表不写入，页面会列出错误行。'),
    ]
    for number, line in help_lines:
        help_sheet.append([number, line])
    help_sheet.column_dimensions['A'].width = 6
    help_sheet.column_dimensions['B'].width = 92
    for row in help_sheet.iter_rows(min_row=2, max_row=help_sheet.max_row):
        row[1].alignment = Alignment(wrap_text=True, vertical='top')

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _existing_names():
    Department = dj_apps.get_model('user', 'Department')
    Role = dj_apps.get_model('user', 'Role')
    User = dj_apps.get_model('user', 'User')
    return (
        set(Department.objects.values_list('name', flat=True)),
        set(Role.objects.values_list('name', flat=True)),
        set(User.objects.values_list('username', flat=True)),
    )


def parse_template(uploaded) -> dict:
    """解析并全量校验上传文件；失败抛 TemplateError(messages)。"""
    if uploaded is None:
        raise TemplateError([_('请选择要上传的模板文件')])
    name = _text(getattr(uploaded, 'name', ''))
    if not name.lower().endswith('.xlsx'):
        raise TemplateError([_('只支持 .xlsx 模板文件')])
    if getattr(uploaded, 'size', 0) > MAX_TEMPLATE_BYTES:
        raise TemplateError([_('模板文件不能超过 %(mb)sMB') % {'mb': MAX_TEMPLATE_MB}])
    try:
        workbook = load_workbook(uploaded, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, ValueError, KeyError, OSError, EOFError):
        raise TemplateError([_('无法读取该文件，请确认是有效的 .xlsx 模板')]) from None

    try:
        sheets = {sheet.title.strip(): sheet for sheet in workbook.worksheets}
    finally:
        workbook.close()

    missing = [title for title in (SHEET_DEPARTMENTS, SHEET_ROLES, SHEET_USERS)
               if title not in sheets]
    if missing:
        raise TemplateError([_('缺少工作表：%(names)s') % {'names': '、'.join(missing)}])

    errors = []
    departments = []
    roles = []
    users = []

    # ---- 部门 ----
    rows = list(sheets[SHEET_DEPARTMENTS].iter_rows(values_only=True))
    if not rows:
        errors.append(_('部门表为空'))
    else:
        columns = _map_headers(rows[0], DEPT_HEADERS)
        if 'name' not in columns:
            errors.append(_('部门表缺少「部门名称」列'))
        else:
            seen = set()
            for number, row in enumerate(rows[1:], start=2):
                name = _cell(row, columns.get('name'))
                parent = _cell(row, columns.get('parent'))
                if not name and not parent:
                    continue
                if not name:
                    errors.append(_('部门表第 %(row)s 行：部门名称不能为空') % {'row': number})
                    continue
                if len(name) > 100:
                    errors.append(_('部门表第 %(row)s 行：部门名称不能超过 100 个字符') % {'row': number})
                    continue
                if name in seen:
                    errors.append(_('部门表第 %(row)s 行：部门「%(name)s」重复') % {'row': number, 'name': name})
                    continue
                if parent and parent == name:
                    errors.append(_('部门表第 %(row)s 行：上级部门不能是自己') % {'row': number})
                    continue
                seen.add(name)
                departments.append({'name': name, 'parent': parent, 'row': number})

    # ---- 角色 ----
    rows = list(sheets[SHEET_ROLES].iter_rows(values_only=True))
    if not rows:
        errors.append(_('角色表为空'))
    else:
        columns = _map_headers(rows[0], ROLE_HEADERS)
        if 'name' not in columns:
            errors.append(_('角色表缺少「角色名称」列'))
        else:
            seen = set()
            requested_codes = set()
            for number, row in enumerate(rows[1:], start=2):
                name = _cell(row, columns.get('name'))
                codes = _split_codes(_cell(row, columns.get('permissions')))
                if not name and not codes:
                    continue
                if not name:
                    errors.append(_('角色表第 %(row)s 行：角色名称不能为空') % {'row': number})
                    continue
                if len(name) > 100:
                    errors.append(_('角色表第 %(row)s 行：角色名称不能超过 100 个字符') % {'row': number})
                    continue
                if name in seen:
                    errors.append(_('角色表第 %(row)s 行：角色「%(name)s」重复') % {'row': number, 'name': name})
                    continue
                seen.add(name)
                roles.append({'name': name, 'permissions': codes, 'row': number})
                requested_codes.update(codes)

            known_perms = set(Permission.objects.filter(
                codename__in=requested_codes).values_list('codename', flat=True))
            unknown = sorted(requested_codes - known_perms)
            if unknown:
                errors.append(_('角色表存在未知权限码：%(codes)s') % {'codes': '、'.join(unknown)})

    # ---- 用户 ----
    rows = list(sheets[SHEET_USERS].iter_rows(values_only=True))
    if not rows:
        errors.append(_('用户表为空'))
    else:
        columns = _map_headers(rows[0], USER_HEADERS)
        if 'account' not in columns:
            errors.append(_('用户表缺少「账号」列'))
        else:
            seen = set()
            for number, row in enumerate(rows[1:], start=2):
                account = _cell(row, columns.get('account'))
                display_name = _cell(row, columns.get('name'))
                dept = _cell(row, columns.get('department'))
                role = _cell(row, columns.get('role'))
                leader = _cell(row, columns.get('leader'))
                if not any((account, display_name, dept, role, leader)):
                    continue
                if not account:
                    errors.append(_('用户表第 %(row)s 行：账号不能为空') % {'row': number})
                    continue
                if len(account) > 150 or not USERNAME_RE.match(account):
                    errors.append(
                        _('用户表第 %(row)s 行：账号只能包含字母、数字、_ . @ + -，且不超过 150 个字符')
                        % {'row': number})
                    continue
                if account in seen:
                    errors.append(_('用户表第 %(row)s 行：账号「%(account)s」重复') % {'row': number, 'account': account})
                    continue
                if len(display_name) > 150:
                    errors.append(_('用户表第 %(row)s 行：姓名不能超过 150 个字符') % {'row': number})
                    continue
                if leader and leader == account:
                    errors.append(_('用户表第 %(row)s 行：直属上级不能是自己') % {'row': number})
                    continue
                seen.add(account)
                users.append({
                    'account': account, 'name': display_name, 'department': dept,
                    'role': role, 'leader': leader, 'row': number,
                })

    if not departments and not roles and not users:
        errors.append(_('模板没有可导入的数据行'))

    existing_depts, existing_roles, existing_accounts = _existing_names()
    dept_names = {item['name'] for item in departments}
    role_names = {item['name'] for item in roles}
    account_names = {item['account'] for item in users}

    # 部门上级必须存在；上传表内部要做环检测，外部已存在部门视为合法父节点。
    parents = {item['name']: item['parent'] for item in departments}
    for item in departments:
        parent = item['parent']
        if parent and parent not in dept_names and parent not in existing_depts:
            errors.append(
                _('部门表第 %(row)s 行：上级部门「%(parent)s」不存在') % {'row': item["row"], 'parent': parent})
    try:
        ordered_departments = _order_departments(parents)
    except ValueError as exc:
        errors.append(str(exc))
        ordered_departments = departments

    # 角色/部门/上级引用必须能在本表或现有数据中找到。
    for item in users:
        if item['department'] and item['department'] not in dept_names \
                and item['department'] not in existing_depts:
            errors.append(
                _('用户表第 %(row)s 行：部门「%(dept)s」不存在') % {'row': item["row"], 'dept': item["department"]})
        if item['role'] and item['role'] not in role_names \
                and item['role'] not in existing_roles:
            errors.append(
                _('用户表第 %(row)s 行：角色「%(role)s」不存在') % {'row': item["row"], 'role': item["role"]})
        if item['leader'] and item['leader'] not in account_names \
                and item['leader'] not in existing_accounts:
            errors.append(
                _('用户表第 %(row)s 行：直属上级「%(leader)s」不存在') % {'row': item["row"], 'leader': item["leader"]})

    if errors:
        raise TemplateError(errors)

    return {
        'departments': ordered_departments,
        'roles': roles,
        'users': users,
    }


def _order_departments(parents: dict) -> list:
    """按上传表内的父子关系排序；父不在上传表时视为已有部门，直接作为根。"""
    by_name = {name: {'name': name, 'parent': parent} for name, parent in parents.items()}
    result = []
    state = {}

    def visit(name):
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            raise ValueError(_('部门层级成环：%(name)s') % {'name': name})
        state[name] = 1
        parent = by_name[name]['parent']
        if parent in by_name:
            visit(parent)
        state[name] = 2
        result.append(by_name[name])

    for name in by_name:
        visit(name)
    return result


__all__ = [
    'MAX_TEMPLATE_MB', 'TemplateError', 'build_template_workbook', 'parse_template',
    'DEFAULT_PASSWORD',
]
