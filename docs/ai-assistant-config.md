# 助手模型配置页

> 对应代码：`plugins/assistant/forms.py`、`plugins/assistant/views.py::settings_page`、`plugins/assistant/llm.py`、`plugins/assistant/models.py::LLMSettings`
> 入口：`/plugins/assistant/settings/`；首页账号菜单「设置 → 通用 → 助手模型 → 配置」

## 一、谁能改

配置页要求 `workspace_manage` 权限（超级用户天然通过）。普通账号直接访问返回 403；首页设置面板里的「助手模型」入口也只对有该权限的账号渲染。

模型地址和 API Key 属于部署级配置，不按用户隔离。修改后对所有账号、下一次请求立即生效，不需要重启容器。

## 二、存哪里、谁优先

五项配置写在 `assistant_llm_settings` 表的单例行（`pk=1`），字段与 `ASSISTANT_LLM_*` 环境变量一一对应：

| 页面字段 | 数据库字段 | 环境变量兜底 |
|---|---|---|
| 接口地址 | `base_url` | `ASSISTANT_LLM_BASE_URL` |
| 模型名 | `model` | `ASSISTANT_LLM_MODEL` |
| API Key | `api_key` | `ASSISTANT_LLM_API_KEY` |
| 超时（秒） | `timeout_seconds` | `ASSISTANT_LLM_TIMEOUT` |
| 输出上限 | `max_tokens` | `ASSISTANT_LLM_MAX_TOKENS` |

读取顺序是**逐字段数据库优先、环境变量兜底**：

- 页面保存过的非空字段覆盖环境变量；
- 数据库里留空的字段继续读环境变量；
- 数据库表还不存在或迁移未应用时，`llm.raw_config()` 捕获数据库错误后直接回退环境变量，首页不会因为配置表缺失白屏。

这样既能从上一轮的 shell 环境注入平滑迁移，也保留“全新部署只配环境变量”的最小路径。

## 三、API Key 的显示与清除

页面**不回显**已保存的 Key：

- 输入框永远为空；
- 已存在 Key 时，字段下方提示“已保存一个 API Key”；
- 留空保存 = 保持原值；
- 勾选「清除已保存的 API Key」再保存 = 写入空字符串。

Key 目前以明文存库（A 阶段未引入加密依赖），所以页面只对 `workspace_manage` 开放，也不把 Key 写进日志或探测结果。后续如果要加密，需要独立迁移和密钥管理，不在 A 阶段内。

## 四、测试连接

「测试连接」用当前表单值发一条最短请求，**不会保存**：

1. 服务端先做与保存相同的字段校验；
2. 用 `llm.probe()` 发一个只带 `ping` 工具的 `chat/completions`；
3. 页面展示：
   - 是否连通；
   - 本次请求耗时（非流式请求，无法切出首 token 时间，这里是整轮耗时）；
   - 本机 / 内网还是公网地址；
   - 服务是否返回了 `tool_calls`；
   - 实际使用的模型名。

失败时只展示统一话术（未配置 / 鉴权失败 / 服务不可达 / 返回格式异常），不把内部地址、Key 或 traceback 带到页面。

## 五、数据流向提示

页面始终显示当前生效地址属于哪一类：

- `127.0.0.1`、`localhost`、`host.docker.internal`、RFC1918 私网、`.local` → 「本机 / 内网」；
- 其他 http/https 地址 → 「公网地址」，并明确提示每轮对话都会把当前用户的业务数据发送到该地址。

这条提示是硬要求：对话落库只说明历史留在本地，不代表推理也在本地。

## 六、运维口径

- 应用迁移：`python manage.py migrate assistant`；
- 查看当前生效配置（不打印 Key）：`python manage.py shell -c "from plugins.assistant import llm; print({k: v for k, v in llm.raw_config().items() if k != 'api_key'})"`；
- 回退到环境变量：把接口地址和模型名同时清空后保存，会删除数据库单例行（含已保存的 Key），完全回到 `ASSISTANT_LLM_*`；也可以在 shell 里删除该行；
- 容器部署后如果只重建、不迁移，配置表不存在，读取会自动回退环境变量，但页面保存会失败；重建后必须执行迁移。

## 七、当前边界

- 只支持 OpenAI 兼容的 `/chat/completions`，不接 Anthropic / Gemini 原生协议；
- 不做模型列表拉取，模型名手工填；
- 不做多配置档案 / 按用户切换；
- 探测是单次请求，不代表并发、长上下文或工具调用稳定性；
- 4B 验收仍以 `docs/ai-assistant-eval.md` 的 20 条固定问句为准，配置页通过不等于验收通过。
