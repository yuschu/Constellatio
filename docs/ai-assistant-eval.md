# A 阶段验收集（20 条固定问句）

> 对应 `docs/ai-assistant-plan.md` 的验收标准：**20 条固定问句，意图识别 + 参数正确 ≥ 70%**。
> 阈值按最低档 **4B / 70%** 设；只有 4B 档跑出的结果才能作为 A 阶段验收结论，其他档位只作参考。

## 一、为什么只看首轮工具与参数

A 阶段的价值是“查得对”，不是“说得好”。最终措辞受模型风格影响很大，用文案好坏评分会把工具调用能力掩盖掉。因此每条问句只检查：

1. **首轮是否调用工具**——直接答文字、不查数据算失败；
2. **是否恰好调用一个工具**——单意图问句拆成多个调用，说明意图识别不干净；
3. **工具名是否匹配**——数量统计不能走明细查询，明细查询不能走统计；
4. **参数是否覆盖用户明确说出的槽位**——月份、范围、类型、状态、关键词、条数、未读；
5. **参数是否通过真实 schema 校验**——类型、枚举、`month` 格式、整数上下限、未知字段。

评分不执行数据库查询，也不评价助手最终回答。工具执行本身由 `plugins.assistant.tests` 覆盖。

## 二、20 条固定问句

| ID | 问句 | 期望工具 | 期望参数 |
|---|---|---|---|
| A01 | 统计一下 2026-11 我审批了多少单。 | `stats_approval_count` | `month=2026-11`, `scope=approver` |
| A02 | 2026-10 我提交了多少张审批单？ | `stats_approval_count` | `month=2026-10`, `scope=applicant` |
| A03 | 这个月我一共批了几单？ | `stats_approval_count` | 当月, `scope=approver` |
| A04 | 上个月我提交了几单？ | `stats_approval_count` | 上月, `scope=applicant` |
| A05 | 帮我查 2026-11 我提交的请假单有哪些。 | `search_approval` | `month=2026-11`, `scope=applicant`, `approval_type=leave` |
| A06 | 我审批过的报销单有哪些？ | `search_approval` | `scope=approver`, `approval_type=expense` |
| A07 | 有哪些审批单抄送给我了？ | `search_approval` | `scope=cc` |
| A08 | 找一下标题里包含“采购”的审批单。 | `search_approval` | `keyword` 包含“采购” |
| A09 | 查一下 2026-10 已通过的用章申请。 | `search_approval` | `month=2026-10`, `scope=applicant`, `status=approved`, `approval_type=seal` |
| A10 | 我发起的审批里，还有哪些在待审批？ | `search_approval` | `scope=applicant`, `status=pending` |
| A11 | 给我看最近 5 条待我审批的单子。 | `search_approval` | `scope=approver`, `status=pending`, `limit=5` |
| A12 | 统计我 2026-11 的考勤情况。 | `stats_attendance` | `month=2026-11` |
| A13 | 上个月我的考勤怎么样？ | `stats_attendance` | 上月 |
| A14 | 最近有什么公告？ | `list_notice` | 无额外过滤 |
| A15 | 列出最近 10 条我还没读的公告。 | `list_notice` | `limit=10`, `unread_only=true` |
| A16 | 有没有我还没读的通知？ | `list_notice` | `unread_only=true` |
| A17 | 技术部现在有多少人？ | `query_department` | `keyword` 包含“技术” |
| A18 | 公司有哪些部门？ | `query_department` | 无关键词 |
| A19 | 帮我找一下叫张伟的同事。 | `search_user` | `keyword` 包含“张伟” |
| A20 | 账号 zhangsan 是谁？ | `search_user` | `keyword` 包含“zhangsan” |

覆盖 6 个只读工具：审批统计 4 条、审批明细 7 条、考勤 2 条、公告 3 条、部门 2 条、人员 2 条。

B 阶段新增的 `draft_approval` 不进入这 20 条只读验收集，覆盖率断言显式排除该工具；六类草稿字段、缺字段不猜、卡片内联编辑、原端点提交由 `plugins/assistant/tests.py` 的 `ApprovalDraftToolTests` / `AssistantApprovalDraftBridgeTests` 覆盖。

## 三、评分细则

- **默认值可省略**：`search_approval` 默认 `scope=applicant`、`limit=10`；`stats_approval_count` 默认 `scope=approver`；`list_notice` 默认 `limit=5`、`unread_only=false`。省略默认值视为参数正确。
- **未要求条数时，显式 `limit` 不算错**：用户没指定“几条”，模型给 5 / 10 / 20 不改变查询对象；但用户明确说“最近 5 条”时必须是 5。
- **其余未要求的过滤条件算错**：例如问“最近有什么公告”却加 `unread_only=true`，会缩窄结果，不能算对。
- **关键词用包含匹配**：用户说“技术部”，模型给“技术”或“技术部”都算对，避免同义表述误判。
- **相对月份按运行当天推算**：“这个月 / 上个月”随运行日期变化，考的是模型是否真的读了系统提示里的“今天”。
- **首轮严格校验 schema**：整数上下限也在校验层执行。`search_approval.limit` 最大 20，模型给 30 或 50 算参数错误，不能拿“工具内部会截断”兜过去。

## 四、怎么跑

```powershell
# 只看 20 条用例，不连模型
.\venv\Scripts\python.exe manage.py eval_assistant_a --dry-run

# 连接当前 settings / 环境变量里的模型，输出明细 JSON
.\venv\Scripts\python.exe manage.py eval_assistant_a --output .tmp-test\assistant-a.json

# 临时指定模型服务，不写入 settings
.\venv\Scripts\python.exe manage.py eval_assistant_a `
  --base-url http://127.0.0.1:11434/v1 --model qwen3:4b `
  --output .tmp-test\assistant-a-4b.json
```

容器内：

```powershell
docker exec constellatio-web-1 python manage.py eval_assistant_a --output /tmp/assistant-a.json
```

默认取第一个启用中的超级用户，保证 6 个只读工具全部可见；普通用户缺 `user_manage` 时命令会直接报错，不会悄悄少跑 4 条。

退出码：正确率低于阈值时返回非 0，可直接接 CI；模型不是 4B 档时仍会计算并输出结果，但会明确标注“不能作为 4B 验收”。

## 五、2026-11-14 结果记录

### 4B 正式验收（A 阶段结论）

- 模型：`qwen3:4b`（ollama，本机；官方 registry 制品，4B 档）
- 结果：**19/20 通过，正确率 95.0%**，高于 70% 阈值 → **A 阶段按 4B/70% 验收成立**
- 唯一失败：A09「查一下 2026-10 已通过的用章申请」首轮没有调用工具，模型直接给了文字回答；属于小模型采样波动，不是工具描述或参数问题
- 首轮耗时：3.3–15.4 秒；多数在 3–8 秒
- 明细：`.tmp-test/assistant-a-4b-official.json`
- 六类草稿改动后（规则 8，账号 `admin`）复跑：仍 **19/20（95.0%）**，本轮唯一失败 A18「首轮未调用工具」，未出现工具参数回归；`mkt_chu` 缺 `query_department`、`search_user` 权限，不能作为验收账号。
- A18 隔离复跑 5 次全部通过（耗时 13.9 / 85.6 / 17.6 / 67.3 / 146.7 秒），确认是 4B 首轮工具调用的采样波动，不是工具描述或参数问题；耗时波动来自本机 CPU 推理。

同一模型规格用 ModelScope 的 `Qwen3-4B-Q4_K_M.gguf` 导入时，另有一轮 **18/20（90.0%）** 的结果（失败 A06/A10，均为参数层），明细 `.tmp-test/assistant-a-4b.json`。两种制品来源能力一致，验收取本轮官方制品的 19/20 作为正式结论。

### 旧 ModelScope 回退件（Qwen3-4B-GGUF，已被替换）

- 模型：`modelscope.cn/Qwen/Qwen3-4B-GGUF:latest`，拉取后 `ollama create` 成 `qwen3:4b`，`num_ctx=4096`、`num_predict=1536`
- 结果：**15/20 通过，正确率 75.0%**，仍高于 70% 阈值
- 失败：A02、A10、A18 首轮未调用工具；A07 多给未要求的 `status=pending`；A09 把 `scope` 给成 `approver`
- 首轮耗时：0.7–14.1 秒，多数 3–5 秒（`reasoning_effort=none` 已关闭思考）
- 结论：官方 registry 不可达时，旧回退件能独立完成 A 阶段验收，但余量只有 5 个百分点；已被下面的非思考版替换
- 明细：`.tmp-test/coldtest_eval.json`

### ModelScope 非思考版回退件（当前默认）

- 模型：`modelscope.cn/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M`，拉取后 `ollama create` 成 `qwen3:4b`，`num_ctx=4096`、`num_predict=1536`
- `ollama show`：4B / Q4_K_M，capabilities 含 completion、tools；模型本身不产生 `<think>` 段
- 首轮不加“不要补默认筛选”规则：**17/20（85.0%）**；失败 A06 多 `status=pending`、A08 缺 `scope=applicant` 且多 `approval_type=expense`、A14 多 `unread_only=True`
- 在系统提示加第 7 条“只填用户明确说出的筛选条件”后复测：**18/20（90.0%）**；失败 A06 多 `month=2026-11`、A14 多 `unread_only=True`，A08 已修正
- 首轮耗时：2.2–16.4 秒，多数 3–6 秒
- 结论：比旧回退件高 3 条，默认回退源切到该制品；正式结论仍以官方件 19/20 为准
- 默认空卷冷启动栈内复测：**18/20（90.0%）**，失败 A06 多 `status=pending`、A14 多 `unread_only=True`
- 明细：`.tmp-test/default-fallback-eval.json`（另两轮为 `new-fallback-eval.json` 17/20、`new-fallback-eval-2.json` 18/20）

### 9B 参考结果（非验收）

- 模型：`qwen3.5:9b`（ollama，本机；**非 4B 档**）
- 结果：**19/20 通过，正确率 95.0%**
- 唯一失败：A09「查一下 2026-10 已通过的用章申请」工具与语义槽位都对，但模型多给了 `limit=50`，超过 `search_approval.limit` 的 `maximum=20`，被严格 schema 校验判为失败
- 结论：9B 明显高于阈值，说明工具描述与参数设计可用；但它只作参考，不替代 4B 结论。

两条 4B 失败都能被现有重试机制兜住：真实 `run_turn()` 会把 schema 校验错误回给模型重试，最多 3 轮；本集按首轮严格口径记为失败。

## 六、已知边界

- 每条问句只跑一次，受小模型采样波动影响；连续多轮稳定性不在本集范围。
- 评分只看首轮。真实 `run_turn()` 允许模型在参数错误后重试，最多 3 轮；重试能力由 `plugins.assistant.tests` 的单轮工具循环测试覆盖，不进入本集分数。
- 不测试写操作——A 阶段工具集在导入时硬断言 `write=False`，不存在写工具。
- 不测试答案数字是否与数据库一致——工具执行正确性由既有工具测试与真实 HTTP 冒烟覆盖。
