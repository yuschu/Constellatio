# 插件开发文档：v1.7.10 对象级越权语义统一（审批详情 / 附件 → 403）

> 关联：`plugins/approval/views.py`（`approval_detail` / `approval_attachment` / `approval_hide`）、`plugin_host/exceptions.py`、`templates/403.html`
> 版本：v1.7.10 · 文档日期：2026-11-11
> 状态：**✅ 已实现**（427 项测试；见 §九）
> 基线：tag `v1.7.9`（420 项测试）
> 语义决策：功能级已在 v1.7.9 统一为 403；**对象级同样用 403**（不用 404），文案用「该审批单不属于你」

## 一、为什么现在做

v1.7.9 把「功能级越权」统一成 403 之后，系统里**还剩第二种越权反馈**：对象级越权仍然 302 回工作台。
这与 v1.7.6 那次的「签到页已发生、审批页潜伏」是同一类问题——两种反馈并存，用户无法区分
「我没这个功能」和「这张单子不是我的」。

## 二、现状清单（实测，`plugins/approval/views.py`）

| 入口 | 行 | 现在的行为 | 语义 |
|---|---|---|---|
| `approval_detail` GET | `_may_view` 为假 → `redirect('index')` | **302** | 对象级越权（非单据相关人） |
| `approval_detail` POST | `_can_act` 为假 → `redirect('index')` | **302** | 对象级越权（可看不可批） |
| `approval_attachment` | `_may_view` 为假 → `redirect('index')` | **302** | 对象级越权（附件下载） |
| `approval_hide` | `get_object_or_404(Approval, pk=…, applicant=request.user)` | **404** | 申请记录的「隐藏」操作；**本版改为 403**（拆成「不存在=404 / 不是我的=403」） |

另外 `approval_detail` 的 POST 分支里有：

```python
except (ValueError, PermissionError):
    # 非法流转 / 非本人审批：静默回到详情
    pass
```

`services` 抛的 `PermissionError` 被吞掉 → 前端看到「什么都没发生」。这是第三种反馈（静默）。

## 三、方案

### 3.1 三个入口：302 → 403（用 v1.7.9 刚修好的 message 透传）

```python
# plugins/approval/views.py
if not _may_view(request.user, approval):
    raise ObjectPermissionDenied('该审批单不属于你')          # 原 redirect('index')

if request.method == 'POST' and not _can_act(request.user, approval):
    raise ObjectPermissionDenied('你无权审批该单据')          # 原 redirect('index')

# approval_attachment：同样用 '该审批单不属于你'
```

- HTML：`ExceptionGuardMiddleware` → `403.html`（固定文案，**不回显** message，v1.7.5 边界不动）；
- JSON（`Accept: application/json` 或 `/stats` 结尾）：`{code: "permission_denied", message: "该审批单不属于你"}`
  —— 正是 v1.7.9 修的 `getattr(exception, 'message', None)` 派上用场的第一处真实场景；
- 日志：`拒绝访问 code=permission_denied msg=该审批单不属于你 GET /plugins/approval/12/`。

### 3.2 `approval_hide` 也改成 403（采纳你的否决，撤回我原来的 404 建议）

我原来的理由是「防存在性探测」，与 §七 自相矛盾：`approval_detail:288` 是
`get_object_or_404(Approval, pk=approval_id)`——不存在 → 404，存在但无权限 → 本版改 403，
**§3.1 落地那一刻存在性就已经可区分了**，`approval_hide` 再保 404 不提供任何保护，只多出第三种反馈。

改法（不能直接 raise，因为原来把「不存在」和「不是我的」并成了一个 404）：

```python
approval = get_object_or_404(Approval, pk=approval_id)      # 不存在 → 404（保持）
if approval.applicant_id != request.user.pk:
    raise ObjectPermissionDenied('该审批单不属于你')          # 不是本人 → 403
```

> 若将来真要防存在性泄露，正确做法是**连 `approval_detail` 一起改 404**（整版重做语义，还要处理
> 「审批人从列表点进详情也 404」），不在本版预算内。

### 3.3 拆开 `except`：`ValueError` 静默、`PermissionError` → 403（采纳你的 B）

核过 `services.py`：`PermissionError` 只在「不是审批人」抛（`:77`），`ValueError` 只在「状态不是待审批」抛
（`:78`）——**两者不同源、不重叠**，「单子刚被别人批了」走的是 `ValueError`。所以我原来「转 403 会误报竞态」
的顾虑不成立。

```python
except ValueError:
    pass                                    # 状态已变等流转竞态：静默（前端二次确认已提示）
except PermissionError as exc:
    # 理论上已被 _can_act 拦住，但不可达分支也不能静默：哪天并发/会签演进到可达必须看得见
    raise ObjectPermissionDenied('你无权审批该单据') from exc
```

顺带改掉 `:309` 的注释——「非本人审批」实际在 `_can_act` 处就被拦了，注释留着会让人以为这里承载越权语义。

## 四、实现清单

| 文件 | 改动 |
|---|---|
| `plugins/approval/views.py` | 三处 `redirect('index')` → `raise ObjectPermissionDenied(...)`；新增 import |
| `plugins/approval/tests.py` / `tests_v155.py` | 受影响的断言同步（302 → 403 + 内容断言），逐条列明 |
| `plugin_host/tests_permission_semantics.py` | 复用现有 403 口径用例（无需新文件） |
| 新增用例 | 5 条，见 §五 |

## 五、测试记录（+7，420 → 427）

新增文件 `plugins/approval/tests_object_permission.py`：

| # | 用例 | 断言 |
|---|---|---|
| 1 | 无关员工 GET 详情 | 403 品牌页；且**不含**「该审批单不属于你」（页面固定文案） |
| 2 | 无关员工 GET 附件 | 403 + `assertNotIsInstance(resp, FileResponse)`（**不能有字节流出**） |
| 3 | 可看不可批（抄送人）POST approve | 403，且单据状态仍 PENDING |
| 4 | 申请人 / 审批人 GET 详情 | 200（防误伤） |
| 5 | 无关员工带 `Accept: application/json` | 403 JSON，`message == '该审批单不属于你'` |
| 6 | 非申请人 POST `approval_hide` | 403，且 `applicant_hidden` 仍为 False（证明没写库） |
| 7 | `services` 抛 `PermissionError`（mock）→ 403 | 走 `except PermissionError` 分支；状态不变 |

原有断言同步 4 处（契约变更，全部补内容断言）：

| 文件 | 用例 | 变化 |
|---|---|---|
| `plugins/approval/tests_authz.py` | `test_stranger_cannot_view_detail` | 302+Location → 403 + 内容 |
| `plugins/approval/tests_authz.py` | `test_stranger_cannot_download_attachment` | 302 → 403 + `assertNotIsInstance(FileResponse)` |
| `plugins/approval/tests_v155.py` | `test_reapply_hide_guard_owner_and_status` | 非申请人 hide 404 → 403 + 「未写库」断言 |
| `plugins/approval/tests_v155.py` | `test_seal_attachment_required_saved_and_downloadable` | 无关人员下载 302 → 403 + 非 FileResponse |

## 六、验收方案

1. 员工 A 拿员工 B 的单据 id 访问详情 / 附件 → **403**（容器 HTTP 实测）；
2. 申请人本人、当前审批人 → 200，且附件可下载；
3. 未登录 → 仍 302 到登录页带 next（v1.7.4 口径不变）；
4. `approval_hide` 非申请人 → 403（不存在仍是 404），且不写 `applicant_hidden`；
5. 门禁三条 + 全量（427），断言同步逐条列明。

## 七、不做 / 已知边界

- 不动 `require_perm`（功能级已在 v1.7.9 统一）。
- 不做 404 伪装（除 `approval_hide`）：审批单在列表里本来就可见，装不存在只会让员工报障。
- 不动 12 处 `@login_required`；不动 `LoginRequiredMiddleware`（匿名 JSON 401 排在本版之后）。
- 其他插件的对象级校验（如有）本版不扫尾，只处理审批详情 / 附件这一组。

## 八、裁定结果（外部 review 已定）

1. `approval_hide`：**改 403**（不是我建议的保 404）——理由见 §3.2。
2. 静默 `PermissionError`：**选 B**（拆开 except）——理由见 §3.3。
3. 文案：**两句都留**——详情/附件「该审批单不属于你」（越权的读）、POST「你无权审批该单据」（越权的写），
   只进 JSON/日志，HTML 页仍是固定文案。

## 九、验收记录（2026-11-11）

### 9.1 测试与门禁

- 新增 7 条用例全绿；同步的 4 处既有断言全绿；
- `ruff` / `check` / `makemigrations --check` 通过；**Ran 427 tests OK**（420 + 7）；
- 全量里剩下的历史抖动（`AttendanceRecordFilterTests`）已在 v1.7.9 收尾修复，本版跑的是修复后的版本。

### 9.2 行为变化

| 入口 | v1.7.9 | v1.7.10 |
|---|---|---|
| 详情 GET（非相关人） | 302 回工作台 | **403** |
| 详情 POST（可看不可批） | 302 回工作台 | **403** |
| 附件下载（非相关人） | 302 回工作台 | **403，且无字节流出** |
| `approval_hide`（非申请人） | 404（与不存在混同） | **403**（不存在仍 404） |
| `services` 抛 `PermissionError` | 静默吞掉 | **403** |
| 详情 POST 遇到 `ValueError`（状态已变） | 静默 | 静默（不变） |

### 9.3 待办

- 匿名访问 JSON 接口仍 302（修点在 `LoginRequiredMiddleware`，v1.7.4 口径）；
- 其他插件的对象级校验未扫尾（本版只处理审批详情 / 附件 / 隐藏）。
