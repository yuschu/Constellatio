"""auth 插件模型：登录失败计数（v1.7.7 / P2）。

背景：v1.7.3 把缓存换成共享 DatabaseCache 后，计数仍是 `cache.get` + `cache.set` 两步，
3 worker 并发时丢更新（自检实测 6 路并发最终计数只有 2/4/4，串行口径应封顶 5）。
这里改成独立计数表 + `select_for_update()` 行锁 + `F()` 无关的单行更新：
- 写入路径在 `transaction.atomic()` 内先锁行再改，跨进程串行；
- sqlite 上 `select_for_update()` 静默退化（不加 FOR UPDATE、不报错），
  与 v1.7.1 区块链链尾锁同一口径：**并发语义只在 MySQL 上成立/可验**。
"""

from django.db import models


class LoginFailureCounter(models.Model):
    """登录失败计数表 auth_login_failure_counter（一人一 IP 一行）。"""

    key = models.CharField('计数键', max_length=64, unique=True)
    count = models.PositiveIntegerField('失败次数', default=0)
    window_started_at = models.DateTimeField('窗口开始时间')

    class Meta:
        db_table = 'auth_login_failure_counter'
        verbose_name = '登录失败计数'
        verbose_name_plural = '登录失败计数'

    def __str__(self):
        return f'{self.key[:8]}…: {self.count}'
