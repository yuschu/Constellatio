"""测试运行器：为测试库补齐数据库缓存表（v1.7.3）。

背景：`CACHES` 默认使用 `DatabaseCache`（跨 worker 共享），但 Django 的测试建库
只创建 `INSTALLED_APPS` 里的模型表，不会创建缓存表；缺表时任何 `cache.*` 调用
直接抛 `OperationalError`（`DatabaseCache._base_set` 开头的 `SELECT COUNT(*)` 在
`try` 之外）。这里在建库之后补一次 `createcachetable`，让测试跑在与生产相同的
共享缓存后端上，而不是把测试改回 LocMem 绕开语义。
"""

from django.core.management import call_command
from django.test.runner import DiscoverRunner


class CacheTableTestRunner(DiscoverRunner):
    """先建测试库，再对 `CACHES` 里所有数据库型缓存建表。"""

    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        # createcachetable 自带幂等（表已存在则跳过），且只会处理 DatabaseCache 型后端。
        # 注意：该命令没有 interactive 选项（只有 args/database/dry_run/verbosity）。
        call_command('createcachetable', verbosity=0)
        return old_config
