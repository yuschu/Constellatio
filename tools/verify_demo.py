#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验演示数据在应用页面上可见、且与论文两张图逐项一致。

用法（项目根目录）：
  venv/Scripts/python.exe tools/verify_demo.py
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plugin_host.settings')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from plugins.attendance.models import Attendance  # noqa: E402
from plugins.blockchain.models import BlockchainRecord  # noqa: E402
from plugins.user.models import User  # noqa: E402

NORMAL = [26, 20, 22, 20, 22, 17, 28, 17, 22, 22, 20, 26, 19, 21, 19, 20, 23, 22, 15, 22, 26, 21]
LATE = [2, 8, 5, 8, 6, 7, 1, 8, 9, 2, 7, 2, 9, 7, 10, 7, 5, 6, 11, 3, 4, 4]
EARLY = [2, 1, 3, 1, 2, 3, 1, 6, 1, 4, 3, 1, 3, 3, 0, 1, 1, 3, 4, 2, 1, 2]
MAKEUP = [1, 1, 0, 0, 0, 2, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1]
DATES = ['09-01', '09-02', '09-03', '09-04', '09-07', '09-08', '09-09',
         '09-10', '09-11', '09-14', '09-15', '09-16', '09-17', '09-18',
         '09-21', '09-22', '09-23', '09-24', '09-25', '09-28', '09-29', '09-30']


def check(label, condition, detail=''):
    if condition:
        print(f'  ✓ {label} {detail}')
    else:
        print(f'  ✗ {label} {detail}')
        raise SystemExit(1)


client = Client()
admin = User.objects.get(username='admin')
client.force_login(admin)
print('[pages]')

# 1) 考勤看板 + 月度统计接口：逐日数组必须等于图4-7
response = client.get('/plugins/attendance/?month=2026-09')
check('GET /plugins/attendance/?month=2026-09', response.status_code == 200,
      f'→ {response.status_code}')

response = client.get('/plugins/attendance/records/?month=2026-09')
check('GET /plugins/attendance/records/?month=2026-09', response.status_code == 200,
      f'→ {response.status_code}')

response = client.get('/plugins/attendance/stats/?month=2026-09')
check('GET /plugins/attendance/stats/?month=2026-09', response.status_code == 200,
      f'→ {response.status_code}')
stats = response.json()
series = {item['key']: item['data'] for item in stats['series']}
index = {day: i for i, day in enumerate(stats['dates'])}
for key, expected in (('normal', NORMAL), ('late', LATE),
                      ('early', EARLY), ('makeup', MAKEUP)):
    got = [series[key][index[day]] for day in DATES]
    check(f'月度统计 {key} 逐日与图4-7一致', got == expected)
check('月度统计记录总数 = 662', stats['totals']['records'] == 662,
      f"→ {stats['totals']['records']}")
check('月度统计 470/131/48/13',
      [stats['totals'][k] for k in ('normal', 'late', 'early', 'makeup')]
      == [470, 131, 48, 13])

# 2) 留痕链页面：总数、校验状态
response = client.get('/plugins/blockchain/')
check('GET /plugins/blockchain/', response.status_code == 200, f'→ {response.status_code}')
html = response.content.decode('utf-8')
chain_ok, broken = BlockchainRecord.verify_chain()
check('留痕链 verify_chain() 通过', chain_ok, f'broken={broken}')
check('留痕总数 693', BlockchainRecord.objects.count() == 693,
      f'→ {BlockchainRecord.objects.count()}')

response = client.get('/plugins/blockchain/stats/?days=90')
check('GET /plugins/blockchain/stats/?days=90', response.status_code == 200,
      f'→ {response.status_code}')
bs = response.json()
plugin_totals = {
    item['key']: sum(item['data']) for item in bs['series']}
print(f'  · 90 天窗口按来源合计：{plugin_totals}')
check('90 天窗口可覆盖全部 693 条', bs['totals']['records'] == 693,
      f"→ {bs['totals']['records']}")
check('90 天窗口来源分布 = 图4-9', plugin_totals == {
    'attendance': 662, 'approval': 24, 'notice': 6, 'structure': 1})

# 3) 其余业务页面可打开
for path in ('/plugins/approval/', '/plugins/notice/', '/plugins/notify/',
             '/plugins/structure/', '/plugins/workspace/'):
    response = client.get(path)
    check(f'GET {path}', response.status_code == 200, f'→ {response.status_code}')

# 4) 直查 DB 分布
print('[db]')
dist = {}
for plugin in BlockchainRecord.objects.values_list('plugin', flat=True):
    dist[plugin] = dist.get(plugin, 0) + 1
check('留痕来源分布 = 图4-9', dist == {
    'attendance': 662, 'approval': 24, 'notice': 6, 'structure': 1}, f'→ {dist}')

from django.db.models import Count  # noqa: E402
status_dist = dict(Attendance.objects.values_list('status').annotate(n=Count('id')))
check('考勤状态分布', status_dist == {
    'normal': 470, 'late': 131, 'early': 48, 'makeup': 13}, f'→ {status_dist}')
print(f'  · 考勤 {Attendance.objects.count()} 条，留痕 {BlockchainRecord.objects.count()} 条')
print('校验通过。')
