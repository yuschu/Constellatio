"""structure 插件：组织关系树（真实账号 + 直属上级），用于责任划分。

数据源是 `user.User.leader`，纯只读计算，不建表、不写数据。
树口径见 docs/plugin-dev-v156.md §二：无上级为根、成环提为根并标记、停用保留。
"""

from django.apps import apps as dj_apps


def _display_name(user):
    return user.last_name or user.username


def _cycle_members(leader_of):
    """返回处于汇报环上的账号 id 集合（A→B→A，含自环）。

    leader_of: {user_id: leader_id 或 None}。用迭代 DFS 染色，避免深链递归。
    """
    color = {}   # 1 = 本次遍历中（灰），2 = 已完成（黑）
    cycle = set()
    for start in leader_of:
        if color.get(start):
            continue
        path, pos, node = [], {}, start
        while node is not None and color.get(node, 0) == 0:
            color[node] = 1
            pos[node] = len(path)
            path.append(node)
            node = leader_of.get(node)
        if node is not None and color.get(node) == 1:
            cycle.update(path[pos[node]:])
        for visited in path:
            color[visited] = 2
    return cycle


def _count_descendants(children, uid):
    """子树账号数（不含本人），带 visited 保护。"""
    total, stack, seen = 0, list(children.get(uid, ())), set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        total += 1
        stack.extend(children.get(current, ()))
    return total


def build_user_tree():
    """构建组织关系树。

    返回 {'roots': [...], 'rows': [...], 'stats': {...}}：
    - roots：根节点（无上级 / 位于汇报环上），children 逐级嵌套；
    - rows：按树先序展开的扁平清单（责任人清单表用）；
    - stats：total / with_leader / roots / cycles / inactive。
    """
    User = dj_apps.get_model('user', 'User')
    users = list(
        User.objects.select_related('department')
        .prefetch_related('roles')
        .order_by('id')
    )
    by_id = {u.pk: u for u in users}

    leader_of = {}
    for u in users:
        # 上级必须是本批账号；自环保留，交给环检测标记后提为根
        leader_of[u.pk] = u.leader_id if u.leader_id in by_id else None
    cycle_ids = _cycle_members(leader_of)

    # 环上节点断开向上边（提为根），其余账号挂到直属上级下
    children = {}
    for uid, leader_id in leader_of.items():
        if leader_id is None or uid in cycle_ids:
            continue
        children.setdefault(leader_id, []).append(uid)

    def make_node(uid, depth, visited):
        user = by_id[uid]
        kids = [kid for kid in children.get(uid, ()) if kid not in visited]
        node = {
            'id': uid,
            'name': _display_name(user),
            'account': user.username,
            'dept': user.department.name if user.department_id else '',
            'roles': [role.name for role in user.roles.all()],
            'is_active': user.is_active,
            'is_cycle': uid in cycle_ids,
            'depth': depth,
            'leader_name': _display_name(by_id[leader_of[uid]])
            if leader_of[uid] not in (None, uid) else '',
            'children': [],
        }
        for kid in kids:
            if kid in visited:
                continue
            node['children'].append(make_node(kid, depth + 1, visited | {uid}))
        node['direct_count'] = len(node['children'])
        node['total_count'] = _count_descendants(children, uid)
        return node

    root_ids = [
        uid for uid, leader_id in leader_of.items()
        if leader_id is None or uid in cycle_ids
    ]
    roots, rows = [], []
    for uid in root_ids:
        node = make_node(uid, 0, frozenset())
        roots.append(node)
        rows.extend(_flatten(node))

    stats = {
        'total': len(users),
        'with_leader': sum(1 for v in leader_of.values() if v is not None),
        'roots': len(roots),
        'cycles': len(cycle_ids),
        'inactive': sum(1 for u in users if not u.is_active),
    }
    return {'roots': roots, 'rows': rows, 'stats': stats}


def _flatten(node, out=None):
    """树 → 先序扁平行。"""
    if out is None:
        out = []
    out.append({
        'id': node['id'],
        'name': node['name'],
        'account': node['account'],
        'dept': node['dept'],
        'roles': node['roles'],
        'leader_name': node['leader_name'],
        'direct_count': node['direct_count'],
        'total_count': node['total_count'],
        'depth': node['depth'],
        'is_active': node['is_active'],
        'is_cycle': node['is_cycle'],
    })
    for child in node['children']:
        _flatten(child, out)
    return out
