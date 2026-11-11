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

## 四、测试计划（+5，433 → 438）

前端没有 JS 测试基建，用**模板渲染断言**钉住关键分支（与 v1.7.11 的做法一致）：

| # | 用例 | 断言 |
|---|---|---|
| 1 | 区块链列表页渲染 | 含 `handleStatsFailure`、含 `response.status === 401`、含 `auth/login` 的 next 拼装 |
| 2 | 考勤记录页渲染 | 同上（两页共用同一 include，防有人只改一处） |
| 3 | 403 文案存在 | 渲染结果含「无权查看该数据」 |
| 4 | 兜底文案存在 | 渲染结果含「数据暂时不可用」 |
| 5 | `handleStatsFailure` 的 403 分支真的传了文案 | 该函数体内出现 `showEmpty('`（带参数的调用形式）；**不断言源码措辞**（改空格/换变量名不该变红） |

> 这 5 条会**因为字符串出现在模板里**而通过，属于弱断言（不做 JS 执行）。真正的验证靠 §五 的容器实测；
> 弱断言的定位是「防回退成 `throw new Error('stats ' + status)` 那种写法」，不是替代行为验证。

## 五、验收（含一条必须真做的人工确认）

| # | 验收项 | 方式 | 记录要求 |
|---|---|---|---|
| 1 | 匿名打开列表页 → 图表区跳登录并带 `next` | **浏览器人工**（无 JS 测试基建，这是本版唯一的行为验证点） | 必须写「已验证 + 时间 + 实际跳转的 URL」；不允许只写「计划验证」 |
| 2 | 权限冻结账号打开两页 | 容器 HTTP + 浏览器 | 显示「无权查看该数据」，页面其它部分正常 |
| 3 | 正常账号 | 浏览器 | 图表正常渲染（回归） |
| 4 | 门禁 + 全量 | `check` / `ruff` / `run_tests_shim.py` | 434 → 439 |
| 5 | 两处 fetch 分支一致 | `diff` 两模板的 fetch 段 | 差异应为 0（同一 include） |

> 第 1 条是本版的核心：v1.7.11 把 401 做出来之后，**只有这一步能证明语义真的落到了界面**。

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

- 草案已按上述裁定修订（`{% load i18n %}`、`next` 硬约束、`null` 哨兵注释、`showEmpty` 不得抛错、
  用例 5 改断言、§五 人工确认改为必做并留记录）。
- **尚未改代码**，等确认后开工。
