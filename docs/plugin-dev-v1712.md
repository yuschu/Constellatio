# 插件开发文档：v1.7.12 前端接过 401 / 403（状态码语义落地到界面）

> 关联：`plugins/blockchain/templates/blockchain/blockchain_list.html`（`load()` 里 fetch）、`plugins/attendance/templates/attendance/attendance_records.html`（同）、新增 `templates/includes/stats_fetch_fail.js`
> 版本：v1.7.12 · 文档日期：2026-11-11
> 状态：**✅ 已实现**（439 项测试；见 §五 实测记录）
> 基线：tag `v1.7.11`（434 项测试）
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

```django
{% load i18n %}{# 必须：{% include %} 是独立编译该模板，父模板的 load 不会继承 #}
function handleStatsFailure(response) {
  if (response.status === 401) {
    // 硬约束：next 只能是**页面 URL**，绝不能用 el.dataset.statsUrl——
    // 那是 /plugins/…/stats/?days=7 这种接口地址，登录后会被扔到一坨 JSON 上。
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

两个钉死点（外部 review 指出，已写进代码注释与 §六 硬约束）：

1. **第一行必须是 `{% load i18n %}`**——`{% include %}` 独立编译被包含模板，父模板的 `{% load %}`
   不会继承；缺这行 → `TemplateSyntaxError: Invalid block tag: 'trans'` → 两个页面直接 500。
2. **`next` 只能拼 `location.pathname + location.search`**，绝不能拼 `el.dataset.statsUrl`。

> 将来若文案里出现单引号（如 `doesn't`），`'{% trans "..." %}'` 会被截断，届时改成
> `{% trans "..." as t %}{{ t|escapejs }}`；当前两句没有引号，不提前折腾。

**empirical 证据**（`venv/v1712_evidence_include_load.py`，四种组合实测）：

```
direct  inc_bad.js (无 load)  → TemplateSyntaxError: Invalid block tag on line 1: 'trans'
include inc_bad.js (父有 load) → TemplateSyntaxError（父模板的 load 不继承）
direct  inc_good.js (自带 load) → OK
include inc_good.js (自带 load) → OK
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

### 2.3 fetch 分支改造（两处各改两行）

不引入 Promise 复杂度，用哨兵值把「已处理」与「无数据」分开：

```js
.then(function (response) {
  // 拿到 response 才谈得上区分状态码；网络层失败（fetch reject）由下面的 .catch 兜
  if (!response.ok) { handleStatsFailure(response); return null; }
  return response.json();
})
.then(function (data) {
  // 哨兵：null 表示「已经被 handleStatsFailure 处理过」。
  // stats 接口**永远返回对象**（没有 null 响应），所以 null 可以安全用作哨兵；
  // 将来若真出现「合法返回 null」的接口，它会被静默跳过、图表空着且无提示。
  if (!data) { return; }
  ...
})
.catch(function () { showFallback(); });
```

- 401 → 跳登录页并带 `next`（保留当前查询串，登录后回到同一筛选）；
- 403 → 表格显示「无权查看该数据」（比「不可用」准确）；
- 其它（500/网络）→ 「数据暂时不可用」；
- **`.catch` 保留**：网络层失败拿不到 response，必须兜底。

> **`showEmpty` 不能抛异常**：若 403 分支里 `showEmpty` 抛错，会落到 `.catch` 的 `showFallback()`，
> 把「无权查看该数据」覆盖成「不可用」，正好抹掉本版要建的区分。实现时 `showEmpty(text)` 只做
> `textContent` 赋值（不读 `dataset.colspan` 之外的任何可能缺失的节点），`fallback` 不存在时直接 return。

## 三、文案与 i18n

| 状态 | 文案 | 说明 |
|---|---|---|
| 401 | 跳转登录页（无文案） | 登录后回原页 |
| 403 | 「无权查看该数据」 | 与后端 403 语义一致 |
| 其他 | 「数据暂时不可用」 | 保持原有兜底语气 |

新增两句都要 `{% trans %}`；`templates/includes/stats_fetch_fail.js` 是模板文件，`{% trans %}` 可正常生效。
英文文案：`No permission to view this data` / `Data temporarily unavailable`。

## 四、测试记录（+5，434 → 439）

新增 `plugin_host/tests_stats_fail_ui.py`，5 条用例：

| # | 用例 | 断言 |
|---|---|---|
| 1 | 区块链列表页接线 | **先 `assertEqual(200)`**（模板语法错误会被 `ExceptionGuardMiddleware` 变成 500，先断言状态码才能一眼定位）→ `assertRegex(r"if \(!response\.ok\)\s*\{\s*handleStatsFailure\(response\)")` → `assertNotIn("throw new Error('stats '")` |
| 2 | 考勤记录页接线 | 同上 |
| 3 | 两页共用同一 include | 两页渲染都含 `response.status === 401` |
| 4 | 403 文案进页面 | 含 `showEmpty(`、`无权查看该数据`、`数据暂时不可用` |
| 5 | 401 的 next 不用接口地址 | 含 `window.location.pathname + window.location.search`；不含 `statsUrl + '?next='` |

两处按 review 意见修正过：

- **断言的是调用点，不是函数定义**：`handleStatsFailure` 这个字符串在 include 的函数定义里本来就有，
  只断言它出现锁不住「fetch 分支被改回 `throw new Error('stats ' ...)`」。`assertRegex` 的
  `if (!response.ok) { handleStatsFailure(response)` 能区分定义（前缀是 `function`）与调用点；
  `assertNotIn("throw new Error('stats '")` 才是正面防回退。
- **`assertEqual(200)` 放第一行**：`ExceptionGuardMiddleware` 会把 `TemplateSyntaxError` 变成 500，
  若先断言字符串，诊断信息会指向「找不到某字符串」，把排查方向带偏。

这些是**弱断言**（不执行 JS）：项目没有前端测试基建，而为一个 4 行分支引入 node+jsdom 不划算（review 结论）。
真正的行为验证见 §五.1。

## 五、验收记录（2026-11-11 11:20 (+08:00)）

| # | 验收项 | 方式 | 结果 |
|---|---|---|---|
| 1 | 401 实际跳转 URL | 渲染后 JS 在 node + 桩 DOM 中执行 | ✅ `location.assign('/plugins/auth/login/?next=%2Fplugins%2Fblockchain%2F%3Fdays%3D30')`（next = 页面 path+query，**不是** stats 接口地址）；考勤页同样为 `…?next=%2Fplugins%2Fattendance%2Frecords%2F%3Fstatus%3Dlate` |
| 2 | 403 分支文案 | 同上 | ✅ `showEmpty('无权查看该数据')` |
| 3 | 其它失败兜底 | 同上（status=500） | ✅ `showEmpty('数据暂时不可用')` |
| 4 | 两页渲染 | 容器 HTTP | ✅ `/plugins/blockchain/`、`/plugins/attendance/records/` 均 200（v1.7.11 已验 stats 接口的 401） |
| 5 | 两处 fetch 分支一致 | include 唯一 | ✅ 两页渲染出的 `handleStatsFailure` 函数体逐字相同（同一个 `templates/includes/stats_fetch_fail.js`） |
| 6 | 门禁 | `check` / `ruff` / 全量 | ✅ **Ran 439 tests OK** |

### 5.1 关于「人工浏览器验证」的口径

review 要求「浏览器打开列表页 → 401 → 跳登录并带 next」必须真做并记录时间。**本环境没有可自动化的浏览器**，
所以我用 `venv/v1712_evidence_stats_fail_js.py` 把**渲染后的** `handleStatsFailure` 抠出来，在 node 里
以桩 DOM 真实执行，捕获 `window.location.assign` / `showEmpty` 的实际入参——这是真实 JS 执行，
只是 DOM 用桩代替，**比字符串断言强、比人工点击弱**。结论按这个口径记录，不冒充浏览器验证。

剩余风险：桩 DOM 不能覆盖「浏览器对 `location.assign` 的处理」以及 CSP 等页面级行为；这两项需真机点击确认，
已在 §七 记为待办。

## 六、不做 / 已知边界

### 6.1 本版新增的两条硬约束（已写入 constraints）

1. **前端 401 跳转的 `next` 只能是页面 URL**（`location.pathname + location.search`），
   禁止拼接接口地址（`el.dataset.statsUrl` 之类）——否则登录后被扔到 JSON 上。
2. **被 `{% include %}` 的模板必须自带 `{% load %}`**——include 独立编译，父模板的 load 不继承。



- 不引入前端构建、不加依赖、不新建 `static/` 目录。
- 不改后端任何状态码语义（v1.7.9 ~ v1.7.11 的口径冻结）。
- 不做全局 fetch 拦截器（只有这两处 stats 请求；等出现第三处再抽）。
- `.catch` 不删：网络层失败没有 response 可判，必须保留兜底。

## 七、裁定结果（外部 review 已定，2026-11-11）

| # | 事项 | 裁定 |
|---|---|---|
| 1 | 两句文案 | 接受；401 不给文案直接跳转也对；403 不带「请联系管理员」是对的（权限冻结是临时态，加这句反而误导） |
| 2 | `next` 用 path+query | 接受，并升级为硬约束（§6.1 第 1 条） |
| 3 | 5 条弱断言 | 接受，但：`{% load i18n %}` 必须进 include 首行（否则两页 500）；用例 5 改断言 `showEmpty('` 的调用形式，**不断言源码措辞** |
| 4 | `_switch_cache` | 单独开 **v1.7.13**，不捆进 v1.8（需要两 worker 容器验证，与模板引擎那版隔开） |

## 八、状态

- ✅ 已实现并验证：两个模板 + 新增 `templates/includes/stats_fetch_fail.js` + 5 条用例 + 渲染后 JS 的 node 实测。
- 门禁 439 项全绿；容器已部署（`docker compose up -d --build`）。
