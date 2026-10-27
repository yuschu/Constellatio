"""structure 插件：职能制公司架构模板定义（代码常量，无业务表）。

部门树、角色清单、用户模板清单。应用逻辑见 services.apply_structure。
"""

# (名称, 上级名称)；上级为 None 表示一级部门
DEPARTMENTS = [
    ('总裁办', None),
    ('总经理办公室', '总裁办'),
    ('人力资源部', None),
    ('招聘组', '人力资源部'),
    ('培训组', '人力资源部'),
    ('薪酬绩效组', '人力资源部'),
    ('财务部', None),
    ('市场部', None),
    ('销售部', None),
    ('研发部', None),
    ('产品组', '研发部'),
    ('设计组', '研发部'),
    ('测试组', '研发部'),
    ('运营部', None),
    ('客服部', None),
    ('行政部', None),
    ('法务部', None),
    ('采购部', None),
    ('信息技术部', None),
    ('运维组', '信息技术部'),
]

# 身份角色（v1.5.4：按 ROLE_PERMISSIONS 授予；经理类可另外授予 user_manage）
ROLES = [
    '总经理',
    '人力资源经理', '财务经理', '市场经理', '销售经理', '研发经理',
    '运营经理', '客服经理', '行政经理', '法务经理', '采购经理', 'IT经理',
    'HRBP', '招聘专员', '培训专员', '薪酬绩效专员', '会计', '出纳',
    '市场专员', '销售专员', '产品经理', 'UI设计师', '研发工程师', '测试工程师',
    '运营专员', '客服专员', '行政专员', '法务专员', '采购专员',
    'IT运维工程师', '系统管理员',
]

# 经理类角色：grant_manager_perms=True 时额外授予 user_manage（L1）
MANAGER_ROLES = {
    '总经理', '人力资源经理', '财务经理', '市场经理', '销售经理', '研发经理',
    '运营经理', '客服经理', '行政经理', '法务经理', '采购经理', 'IT经理',
}

# v1.5.4：角色权限模板（除全员基线 attendance_view/attendance_check/notice_view 外）
STAFF_PERMS = {'approval_view'}
MANAGER_PERMS = {
    'approval_view', 'approval_approve', 'attendance_report_view',
    'notice_manage', 'blockchain_view', 'structure_view',
}
HRBP_PERMS = {'approval_view', 'attendance_report_view', 'structure_view'}
SYSTEM_ADMIN_PERMS = {
    'user_manage', 'workspace_manage', 'structure_manage', 'structure_view',
    'blockchain_view', 'blockchain_verify', 'attendance_report_view',
    'notice_manage', 'approval_view', 'approval_approve',
    # v1.7.2：考勤规则设置（影响全员迟到/早退口径）
    'attendance_rule_manage',
}

# 角色 → 权限码集合（应用模板时幂等补齐，只增不减）
ROLE_PERMISSIONS = {}
for _role_name in ROLES:
    if _role_name in MANAGER_ROLES:
        ROLE_PERMISSIONS[_role_name] = set(MANAGER_PERMS)
    elif _role_name == 'HRBP':
        ROLE_PERMISSIONS[_role_name] = set(HRBP_PERMS)
    elif _role_name == '系统管理员':
        ROLE_PERMISSIONS[_role_name] = set(SYSTEM_ADMIN_PERMS)
    else:
        ROLE_PERMISSIONS[_role_name] = set(STAFF_PERMS)
# 总经理是最高管理岗：模板权限外再授用户与组织管理（L1）
ROLE_PERMISSIONS['总经理'] = set(MANAGER_PERMS) | {'user_manage'}

ALL_ROLE_PERMISSION_CODES = set().union(*ROLE_PERMISSIONS.values())

# 用户模板：(账号, 姓名, 部门, 角色)；密码统一 constellatio123
USERS = [
    ('gm_zhang', '张总', '总裁办', '总经理'),
    ('hr_wang', '王经理', '人力资源部', '人力资源经理'),
    ('hr_zhao', '赵HR', '招聘组', 'HRBP'),
    ('hr_qian', '钱招聘', '招聘组', '招聘专员'),
    ('hr_sun', '孙培训', '培训组', '培训专员'),
    ('hr_li', '李薪酬', '薪酬绩效组', '薪酬绩效专员'),
    ('fin_zheng', '郑经理', '财务部', '财务经理'),
    ('fin_wu', '吴会计', '财务部', '会计'),
    ('fin_chen', '陈出纳', '财务部', '出纳'),
    ('mkt_feng', '冯经理', '市场部', '市场经理'),
    ('mkt_chu', '褚市场', '市场部', '市场专员'),
    ('sal_wei', '卫经理', '销售部', '销售经理'),
    ('sal_jiang', '蒋销售', '销售部', '销售专员'),
    ('rd_han', '韩经理', '研发部', '研发经理'),
    ('rd_yang', '杨产品', '产品组', '产品经理'),
    ('rd_zhu', '朱研发', '研发部', '研发工程师'),
    ('rd_yan', '闫测试', '测试组', '测试工程师'),
    ('rd_qin', '秦设计', '设计组', 'UI设计师'),
    ('ops_lin', '林经理', '运营部', '运营经理'),
    ('ops_he', '何运营', '运营部', '运营专员'),
    ('cs_xu', '徐经理', '客服部', '客服经理'),
    ('cs_gao', '高客服', '客服部', '客服专员'),
    ('adm_huang', '黄经理', '行政部', '行政经理'),
    ('adm_liang', '梁行政', '行政部', '行政专员'),
    ('legal_liu', '刘经理', '法务部', '法务经理'),
    ('legal_shi', '施法务', '法务部', '法务专员'),
    ('pur_du', '杜经理', '采购部', '采购经理'),
    ('pur_xiao', '肖采购', '采购部', '采购专员'),
    ('it_cai', '蔡经理', '信息技术部', 'IT经理'),
    ('it_luo', '罗运维', '运维组', 'IT运维工程师'),
    ('it_zhou', '周系统', '信息技术部', '系统管理员'),
]

DEFAULT_PASSWORD = 'constellatio123'

# 直属上级（v1.5.5）：账号 → 上级账号；用于审批人留空时的自动指派与抄送
LEADER_OF = {
    'gm_zhang': None,
    # 一级部门负责人 → 总经理
    'hr_wang': 'gm_zhang', 'fin_zheng': 'gm_zhang', 'mkt_feng': 'gm_zhang',
    'sal_wei': 'gm_zhang', 'rd_han': 'gm_zhang', 'ops_lin': 'gm_zhang',
    'cs_xu': 'gm_zhang', 'adm_huang': 'gm_zhang', 'legal_liu': 'gm_zhang',
    'pur_du': 'gm_zhang', 'it_cai': 'gm_zhang',
    # 组内成员 → 部门负责人
    'hr_zhao': 'hr_wang', 'hr_qian': 'hr_wang', 'hr_sun': 'hr_wang', 'hr_li': 'hr_wang',
    'fin_wu': 'fin_zheng', 'fin_chen': 'fin_zheng',
    'mkt_chu': 'mkt_feng', 'sal_jiang': 'sal_wei',
    'rd_yang': 'rd_han', 'rd_zhu': 'rd_han', 'rd_yan': 'rd_han', 'rd_qin': 'rd_han',
    'ops_he': 'ops_lin', 'cs_gao': 'cs_xu', 'adm_liang': 'adm_huang',
    'legal_shi': 'legal_liu', 'pur_xiao': 'pur_du',
    'it_luo': 'it_cai', 'it_zhou': 'it_cai',
}


def dept_tree():
    """部门树：[(dept, [children...]), ...] 保持模板顺序。"""
    children = {}
    for name, parent in DEPARTMENTS:
        children.setdefault(parent, []).append(name)
    return [(name, children.get(name, [])) for name in children.get(None, [])]
