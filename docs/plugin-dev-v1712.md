# 插件开发文档：v1.7.12 前端接过 401 / 403（状态码语义落地到界面）

> 关联：`plugins/blockchain/templates/blockchain/blockchain_list.html`（`load()` 里 fetch）、`plugins/attendance/templates/attendance/attendance_records.html`（同）、新增 `templates/includes/stats_fetch_fail.js`
> 版本：v1.7.12 · 文档日期：2026-11-11
> 状态：**草案 —— 待审**
> 基线：tag `v1.7.11`（433 项测试全绿）
> 目标：v1.7.9 / v1.7.10 / v1.7.11 把后端分成 302 / 401 / 403 / 404 之后，**前端第一次真正用上这些判据**

## 一、问题（你指出的，属实）

两处 `fetch` 现在的写法一模一样：

```js
.then(function (response) {
  if (!response.ok) { throw new Error('stats ' + response.status); }
  return response.json();
})
...
.catch(function () { showFallback(); });
```

于是无论后端给 302（跟随登录页 HTML）、401、403 还是 500，**用户看到的都是同一个「图表不可用」**：

| | 后端 | 前端 | 用户 |
|---|---|---|---|
| v1.7.11 之前 | 302 → fetch 跟随 → 登录页 200 HTML | `response.ok` 为真 → `.json()` 解析炸 → catch | 「图表不可用」 |
| v1.7.11 之后 | 401 JSON | `!response.ok` → throw → catch | **「图表不可用」（一模一样）** |

结论：v1.7.11 提供了判据，但没有任何一行代码消费它。

## 二、方案

### 2.1 抽公共函数（一次实现，两处调用）

新文件 `templates/includes/stats_fetch_fail.js`（**模板 include，不是静态资源**：项目没有项目级
`static/` 目录，为三行 JS 去改 `STATICFILES_DIRS` 不划算；两个模板都用内联脚本，`{% include %}` 正好复用）：

```js
// 依赖调用方已定义 showEmpty(text) 与 fallback 容器
function handleStatsFailure(response) {
  if (response.status === 401) {
    window.location.assign('{% url "auth:login" %}?next=' +
      encodeURIComponent(window.location.pathname + window.location.search));
    return true;
  }
  if (response.status === 403) {
    showEmpty('{% trans "无权查看该数据" %}');
    return true;
  }
  showEmpty('{% trans "数据暂时不可用" %}');
  return true;
}
```

### 2.2 两个模板的 `showEmpty` 支持文案参数

现在 `showEmpty()` 固定用 `fallback.dataset.empty`；改成 `showEmpty(text)`：

```js
function showEmpty(text) {
  ...
  cell.textContent = text || fallback.dataset.empty || '';
  ...
}
```

调用点：
- 数据为空时 `showEmpty()` → 仍显示「该时间范围内暂无留痕记录」；
- 403 时 `showEmpty('无权查看该数据')`；
- 其它失败 `showEmpty('数据暂时不可用')`。

### 2.3 fetch 分支改造（两处各改一行 + 一行）

```js
}).then(function (response) {
  if (!response.ok) { return handleStatsFailure(response).then(...)? }
```
不引入 Promise 复杂度，直接：

```js
.then(function (response) {
  if (!response.ok) { handleStatsFailure(response); return null; }
  return response.json();
})
.then(function (data) {
  if (!data) { return; }        // 已经被 handleStatsFailure 处理
  ...
})
.catch(function () { showFallback(); });
```

- 401 → 跳登录页并带 `next`（保留当前查询串，登录后回到同一筛选）；
- 403 → 表格里显示「无权查看该数据」（比「不可用」准确）；
- 其它（500/网络）→ 「数据暂时不可用」；
- **`.catch` 保留**：网络层失败（fetch 直接 reject，拿不到 response）仍走 `showFallback()`。

## 三、文案与 i18n

| 状态 | 文案 | 说明 |
|---|---|---|
| 401 | 跳转登录页（无文案） | 登录后回原页 |
| 403 | 「无权查看该数据」 | 与后端 403 语义一致 |
| 其他 | 「数据暂时不可用」 | 保持原有兜底语气 |

新增两句都要 `{% trans %}`；`templates/includes/stats_fetch_fail.js` 是模板文件，`{% trans %}` 可正常生效。
英文文案：`No permission to view this data` / `Data temporarily unavailable`。

## 四、测试计划（+5，433 → 438）

前端没有 JS 测试基建，用**模板渲染断言**钉住关键分支（与 v1.7.11 的做法一致）：

| # | 用例 | 断言 |
|---|---|---|
| 1 | 区块链列表页渲染 | 含 `handleStatsFailure`、含 `response.status === 401`、含 `auth/login` 的 next 拼装 |
| 2 | 考勤记录页渲染 | 同上（两页共用同一 include，防有人只改一处） |
| 3 | 403 文案存在 | 渲染结果含「无权查看该数据」 |
| 4 | 兜底文案存在 | 渲染结果含「数据暂时不可用」 |
| 5 | `showEmpty(text)` 支持参数 | 渲染结果含 `text \|\| fallback.dataset.empty` |

> 这 5 条会**因为字符串出现在模板里**而通过，属于弱断言（不做 JS 执行）。真正的验证靠 §五 的容器实测；
> 弱断言的定位是「防回退成 `throw new Error('stats ' + status)` 那种写法」，不是替代行为验证。

## 五、验收方案

1. 容器里用**匿名**请求 `/plugins/blockchain/stats/`（`Accept: application/json`）→ 401 JSON（v1.7.11 已验）；
   浏览器打开列表页 → 图表区域出现跳转登录（人工确认一次）；
2. 用**权限冻结**账号打开两页 → 图表区域显示「无权查看该数据」，且页面其它部分正常；
3. 正常账号 → 图表正常渲染（回归）；
4. 门禁三条 + 全量 438；
5. 两个模板的 fetch 分支代码**完全一致**（同一个 include），用 diff 证明。

## 六、不做 / 已知边界

- 不引入前端构建、不加依赖、不新建 `static/` 目录。
- 不改后端任何状态码语义（v1.7.9 ~ v1.7.11 的口径冻结）。
- 不做全局 fetch 拦截器（只有这两处 stats 请求；等出现第三处再抽）。
- `.catch` 不删：网络层失败没有 response 可判，必须保留兜底。

## 七、待审确认

1. 「无权查看该数据」/「数据暂时不可用」两句文案是否可用？
2. 401 跳转时 `next` 用「当前 path+query」还是只用 pathname？（我倾向 path+query，登录后保留筛选）
3. §四 的 5 条模板字符串断言是否接受（弱断言），还是本版只做 §五 的容器实测、不新增测试？
