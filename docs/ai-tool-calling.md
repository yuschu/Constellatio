# 本地模型的工具调用实现

> 配套文档：`docs/ai-assistant-plan.md`（阶段定义与架构）、`docs/dsh-visual-spec.md`（视觉基线）。
> 本文只讲一件事：**用户说一句话，怎么变成一次真实的 OA 操作，以及在哪一步拦住它**。

## 一、前置条件：服务端必须真的会吐 tool_calls

这不是"模型聪明就行"的事，是**推理服务的开关问题**。两个实测坑：

| 后端 | 必须做的 | 不加会怎样 |
|---|---|---|
| **llama.cpp server** | 启动加 `--jinja` | **tool calling 完全不工作**，模型只吐纯文本，你以为它"不会用工具"——其实是你没开。这是最常见的踩坑点 |
| **ollama** | 无需额外开关，原生支持 | — |

**Qwen 系列的一个已知不兼容**：Qwen 官方文档明确写了"我们采用的格式目前和 Ollama 的 tool call parser 配合得不好"。表现是 `tool_calls` 字段缺失或 `arguments` 不是合法 JSON。

**所以校验层不是可选项**（见 §四）。不要假设服务端吐出来的东西一定合规。

**部署自检**（写进配置页的"测试连接"）：

```
POST {base_url}/chat/completions
{
  "model": "{model}",
  "messages": [{"role": "user", "content": "查一下张三的信息"}],
  "tools": [<一个最简单的工具定义>],
  "tool_choice": "auto"
}

检查返回：
① HTTP 200 ？
② choices[0].message.tool_calls 存在 ？
③ function.arguments 是合法 JSON ？
三项任一失败 → 提示"当前服务不支持工具调用"，而不是静默降级成纯聊天
```

## 二、一次完整的调用链路

```
用户："这个月我批了几个单"
  │
  ├─① 术语表命中？
  │     "审批" → 已知术语，但"批了几个单"是统计意图，不是单条查询 → 未命中，往下走
  │
  ├─② 构造 messages + tools
  │     messages = [system(角色/权限/今天日期), ...历史, user(这句话)]
  │     tools    = [search_approval, stats_approval_count, ...]（按角色过滤后）
  │
  ├─③ POST /v1/chat/completions
  │     返回 tool_calls = [{
  │       id: "call_a1",
  │       function: { name: "stats_approval_count",
  │                   arguments: '{"month":"2026-11","approver":"self"}' }
  │     }]
  │
  ├─④ 服务端校验（见 §四）
  │     name 在允许列表 ？ ✓
  │     arguments 是合法 JSON ？ ✓
  │     必填参数齐全 ？ ✓
  │     参数值域合法（month 格式、approver 是 self/用户ID）？ ✓
  │
  ├─⑤ 权限判定
  │     stats_approval_count.required_permissions = ['approval_view']
  │     registry._user_perm_codenames(request.user) 是否含 approval_view ？
  │     → 不含则拒绝，返回"你没有查看审批的权限"，不进 ⑥
  │
  ├─⑥ 执行工具（A 阶段：只读 ORM 查询）
  │     返回 {"approved": 12, "rejected": 2}
  │
  ├─⑦ 结果回填，二次请求模型让它用人话解释
  │     messages += [
  │       {role:"assistant", tool_calls:[...]},
  │       {role:"tool", tool_call_id:"call_a1", content:'{"approved":12,"rejected":2}'}
  │     ]
  │     → 模型返回："本月你审批通过 12 单，驳回 2 单。"
  │
  └─⑧ 落库（Conversation/Message）+ 返回前端
```

**轮次上限**：整个循环最多 **3 轮**（初判 + 一次工具结果 + 一次补调）。超过 3 轮直接返回"这个问题我需要你更明确地描述"，不要让它无限自我循环。

## 三、工具定义（真实 schema）

OpenAI 标准格式，字段固定不可改：

```json
{
  "type": "function",
  "function": {
    "name": "search_approval",
    "description": "按条件查询审批单。只读，不修改任何数据。用户问『有哪些单子』『某个单的状态』时使用。",
    "parameters": {
      "type": "object",
      "properties": {
        "approval_type": {
          "type": "string",
          "enum": ["leave", "expense", "seal", "outing", "overtime", "comp", "dept_delete", "user_disable"],
          "description": "审批类型，取值见枚举。不确定就不要填"
        },
        "status": {
          "type": "string",
          "enum": ["pending", "approved", "rejected"],
          "description": "状态"
        },
        "month": {
          "type": "string",
          "description": "月份，严格格式 YYYY-MM，例如 2026-11"
        },
        "keyword": { "type": "string", "description": "标题关键词" }
      },
      "required": []
    }
  }
}
```

**`enum` 必须写全**——这是给小模型最重要的约束。不写 enum，模型会自己编一个 `"出差"`、`"报销单"` 这种它以为对的类型名，然后你的后端查不到。

**取值以真实模型为准**：`plugins/assistant/tools.py` 在导入时直接读 `Approval.Type.choices` 生成 enum（小写，且没有 `PURCHASE`）。文档历史示例曾写成大写 + `PURCHASE`，已按真实模型修正；A 阶段测试 `test_approval_enum_uses_real_model_values` 守住这条。

**范围与可见性**：`scope=applicant` 与「我的申请」同口径，过滤 `applicant_hidden`——用户主动隐藏或被替换的驳回单不再被助手翻出来；`approver` / `cc` 只按当前用户的审批人、抄送人关系过滤。

**description 用中文写**，而且要写"什么时候用 / 什么时候不用"。小模型对 description 的依赖远高于大模型。

**每个工具的元数据里带两样东西**（不放进 schema，放 Python 侧）：

```python
TOOLS = {
    "search_approval": {
        "fn": tools_query.search_approval,
        "required_permissions": ["approval_view"],
        "write": False,                    # A 阶段必须全为 False，代码层断言
        "max_calls_per_turn": 1,
    },
    "stats_approval_count": {
        "fn": tools_query.stats_approval_count,
        "required_permissions": ["approval_view"],
        "write": False,
        "max_calls_per_turn": 1,
    },
}
```

**A 阶段的硬断言**（可写成测试）：

```python
assert all(not t["write"] for t in TOOLS.values()), "A 阶段不允许存在写工具"
```

## 四、服务端校验层（小模型场景的核心）

**这是整个实现里最容易被跳过、也最容易出事的一层。** 4B 级模型的输出常态是：

| 失败模式 | 表现 | 概率 |
|---|---|---|
| `arguments` 不是合法 JSON | 少引号、多逗号、中文引号 | 高 |
| 参数名幻觉 | 给出 schema 里没有的字段 | 中 |
| 参数值幻觉 | 编一个不存在的部门/类型/月份 | 高 |
| 该调工具却直接答复 | 返回纯文本"我不太确定" | 中 |
| 该答复却硬调工具 | 为了"显得能干"乱调 | 低 |
| 一次返回多个 tool_calls | 并发调 5 个工具 | 低但危险 |

**校验必须逐条做，任何一条不过就带错误信息重试，最多 2 次**：

```python
def validate_tool_call(tc, user, allowed_names, turn_state):
    """返回 (ok, args_or_error)。失败时 error 会拼进 messages 让模型重来。"""
    # 1. 工具名
    name = tc["function"]["name"]
    if name not in allowed_names:
        return False, f"工具 {name} 不存在。可用工具：{sorted(allowed_names)}"

    # 2. 参数是合法 JSON
    raw = tc["function"]["arguments"]
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return False, 'arguments 必须是合法 JSON，例如 {"month":"2026-11"}'
    if not isinstance(args, dict):
        return False, "arguments 必须是 JSON 对象"

    # 3. 字段名白名单（防幻觉字段）
    spec = TOOLS[name]["schema"]["properties"]
    extra = set(args) - set(spec)
    if extra:
        return False, f"这些参数不存在：{sorted(extra)}。只允许：{sorted(spec)}"

    # 4. 类型与枚举
    for k, v in args.items():
        declared = spec[k]
        if "enum" in declared and v not in declared["enum"]:
            return False, f"参数 {k} 只能是 {declared['enum']}，你给的是 {v!r}"

    # 5. 值域：日期格式、ID 存在性
    if "month" in args and not re.fullmatch(r"\d{4}-\d{2}", str(args["month"])):
        return False, f"month 必须是 YYYY-MM 格式，你给的是 {args['month']!r}"

    # 6. 单轮调用次数上限
    if turn_state["calls"].get(name, 0) >= TOOLS[name]["max_calls_per_turn"]:
        return False, f"工具 {name} 本轮已调过，不要重复调用"

    # 7. 权限（放最后，避免把权限信息泄露给模型）
    if not has_perms(user, TOOLS[name]["required_permissions"]):
        return False, "__DENIED__"      # 不走重试，直接回拒绝话术

    return True, args
```

**两个设计要点**：

- **权限判定放最后**，且用哨兵值 `__DENIED__` 区分——权限不足**不该让模型重试**，因为重试也解决不了，而且把"缺哪个权限"写进 messages 等于给模型喂越权提示。
- **重试要带具体错误**，不要只说"你错了"。小模型靠错误信息自纠的能力有限，但给得越具体成功率越高（尤其 enum 和格式类错误）。

## 五、执行循环（零新增依赖）

用标准库 `urllib.request`，不引 requests：

```python
import json, urllib.request, urllib.error

def call_llm(cfg, messages, tools=None, timeout=30):
    payload = {"model": cfg["model"], "messages": messages, "temperature": 0.2}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    req = urllib.request.Request(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_turn(cfg, user, messages, tools, allowed_names, max_rounds=3):
    """一次用户输入 → 最终回答。返回 (reply_text, tool_logs)。"""
    logs = []
    for _ in range(max_rounds):
        resp = call_llm(cfg, messages, tools)          # 失败由外层兜底
        msg = resp["choices"][0]["message"]

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return msg.get("content") or "", logs   # 纯文本，收工

        messages.append({"role": "assistant", "tool_calls": tool_calls})

        for tc in tool_calls[:3]:                  # 硬上限 3，防并发爆炸
            ok, args = validate_tool_call(tc, user, allowed_names, {"calls": {}})
            if not ok and args == "__DENIED__":
                return "你没有执行这个操作所需的权限。", logs
            if not ok:
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": json.dumps({"error": args}, ensure_ascii=False),
                })
                continue
            result = TOOLS[tc["function"]["name"]]["fn"](user, **args)
            logs.append({"tool": tc["function"]["name"], "args": args})
            messages.append({
                "role": "tool", "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return "这个问题我没法确定，能再说具体一点吗？", logs
```

**为什么 A 阶段用非流式**：Django 视图是同步的，流式要 `StreamingHttpResponse` + SSE，还要处理 CSP 与前端事件绑定。工具调用本身要"停一下等结果"，流式价值不大。**先把正确性做出来，B 阶段再考虑流式。**

**超时策略**：连接超时 5 秒，读超时 30 秒。400 级错误不带错误码的情况下，**不要在页面上显示原文**（可能含内部地址），只显示"模型服务返回错误"。

## 六、A / B / C 三档在链路里差在哪

**关键设计：三档的差别不在模型侧，在工具实现。**

| | A 只读 | B 建议-确认 | C 直接操作 |
|---|---|---|---|
| 工具集 | `search_*` / `stats_*` / `list_*` | 加 `draft_*` | 加 `create_*` / `update_*` |
| 工具返回 | 查询结果 | **草稿对象**（不落库） | 真实执行结果 |
| ⑥ 之后 | 直接 ⑦ 解释结果 | 返回草稿 → 前端渲染可编辑卡片 → 用户点提交 → 走**原有视图函数** | 执行 → 二次确认 → 审计 |
| 模型知不知道自己在 B 还是 C | **不知道** | 不知道 | 不知道 |
| 越权防线 | 权限判定 | 权限判定 + 人工闸门 | 权限判定 + 人工闸门 + 审计 |

`create_approval` 这个工具名在 B 阶段实现成"构造 Approval 对象但不 save"，C 阶段实现成"调用 `approval.views.create` 的同一段逻辑并 save"。**从模型视角完全一样**，所以升级只换工具实现，prompt 和 schema 一个字不用改。

**代价**：B 阶段的"草稿"必须能被前端编辑。这要求草稿的字段结构 == 表单的字段结构。如果两者不一致，用户改完提交会对不上。所以 `draft_*` 工具返回的字段名必须**直接就是表单字段名**，不能自己起一套。

**B 阶段提交必须走原视图函数的原因**：这样审批的权限校验、审计字段填充（`AuditModel`）、留痕链路全部自动继承。自己新写一条 save 路径，等于绕开了 v1.7.16 那套安全加固。

## 七、失败模式与兜底

| 失败 | 检测 | 处置 |
|---|---|---|
| 服务不可达 | `urllib.error.URLError` / 连接超时 | 3 秒内返回"助手暂不可用"，**页面其余部分照常工作** |
| 401/403 | HTTPError code | 显示"模型服务鉴权失败，请检查 API Key" |
| 返回不是 JSON | `json.JSONDecodeError` | 显示"模型服务返回格式异常" |
| 没有 `tool_calls` 且内容为空 | 字段检查 | 重试一次，再失败则返回"没听清" |
| 3 轮耗尽 | 循环计数 | 返回"请说得更具体" |
| 工具抛异常 | `except Exception` 包住单次执行 | 把异常类型（不含 traceback）作为 tool 结果回给模型，让它换方式；**不吞异常** |
| 模型编造了不存在的 ID | 工具内部 `Model.DoesNotExist` | 作为 tool 结果返回"未找到"，让它重试 |

**一条硬规矩**：模型服务的任何失败都**不能导致首页打不开**。首页视图要先把静态骨架渲染出来，模型调用放在后面或异步，失败就显示占位提示。

## 八、明确不做

- **不做流式**（A/B 阶段）。理由见 §五。
- **不做多工具并发**。单轮最多 3 个 tool_call，且顺序执行。
- **不做自动重试整个对话**。只重试单次工具调用校验失败。
- **不让模型看到权限码**。权限失败只说"没有权限"，不说"缺 approval_view"。
- **不在 A/B 阶段出现任何 `write: True` 的工具**，代码层断言守住。
- **不把 traceback 或内部地址返回给前端**。
