"""插件间通信总线：跨插件交互一律走信号，禁止直接 import 对方模型。

各业务插件在"关键操作"处 send() 对应信号；
blockchain 等订阅方统一 connect()，不反向依赖任何业务插件。
"""

from django.dispatch import Signal

# 全局业务信号
approval_finished = Signal()      # 审批结束（发起/通过/驳回），携带 approval_id, result
notice_published = Signal()       # 公告发布，携带 announcement_id
attendance_checked = Signal()     # 打卡成功，携带 user_id, date
user_created = Signal()           # 用户创建，携带 user_id
user_updated = Signal()           # 用户更新，携带 user_id
plugin_toggled = Signal()         # 插件开关切换，携带 app_key, enabled, operator_id
