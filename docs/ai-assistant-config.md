# 助手模型配置页

> 对应代码：`plugins/assistant/forms.py`、`plugins/assistant/views.py::settings_page`、`plugins/assistant/llm.py`、`plugins/assistant/models.py::LLMSettings`、`plugins/assistant/crypto.py`
> 入口：`/plugins/assistant/settings/`；首页账号菜单「设置 → 通用 → 助手模型 → 配置」

## 一、默认就是内置模型

`docker compose up -d --build` 会同时拉起 `ollama` 服务；`ollama-init` 在 Ollama 健康后把 `OLLAMA_MODEL`（默认 `qwen3:4b`）拉进 `ollama_data` 卷。Web 默认连 `http://ollama:11434/v1`，所以全新部署不需要再填地址和模型，打开首页就能对话。

- 模型卷约占 2–3 GB；首次启动需要联网拉取，耗时取决于网络。
- 已存在模型时 `ollama-init` 跳过拉取，不再请求 registry；随后仍会做一次最小生成预热。
- 预热会把 4B 载入 `ollama` 内存（`OLLAMA_KEEP_ALIVE` 默认 30 分钟），Web 等预热结束才启动。CPU 冷加载约 30–45 秒，这一步把等待放在启动阶段，而不是用户第一次提问。
- 内置 Ollama 默认跑 CPU，4B 生成约 7 token/s；一次带工具调用的问答实测约 3 分钟。Compose 默认 `ASSISTANT_LLM_TIMEOUT=240`，低于 120 秒容易在思考段未结束时被掐断。
- Web 等 `ollama-init` 成功退出后才启动：模型没拉下来时 Web 不会带病对外服务，看 `docker compose logs ollama-init` 定位，修好网络后重跑 `docker compose up -d`。
- Docker Hub 不可达时用 `OLLAMA_IMAGE` 指向可用的镜像源（保持同一 tag），例如 `OLLAMA_IMAGE=<镜像站>/ollama/ollama:0.40.11`。

配置页是**覆盖入口**，不是必填项：内置服务跑通后，管理员仍可在这里改成公司网关、GPU 机器或更大的模型。

## 二、谁能改

配置页要求 `workspace_manage` 权限（超级用户天然通过）。普通账号直接访问返回 403；首页设置面板里的「助手模型」入口也只对有该权限的账号渲染。

模型地址和 API Key 属于部署级配置，不按用户隔离。修改后对所有账号、下一次请求立即生效，不需要重启容器。

## 三、存哪里、谁优先

五项配置写在 `assistant_llmsettings` 表的单例行（`pk=1`），字段与 `ASSISTANT_LLM_*` 环境变量一一对应：

| 页面字段 | 数据库字段 | 环境变量兜底 |
|---|---|---|
| 接口地址 | `base_url` | `ASSISTANT_LLM_BASE_URL` |
| 模型名 | `model` | `ASSISTANT_LLM_MODEL` |
| API Key | `api_key` | `ASSISTANT_LLM_API_KEY` |
| 超时（秒） | `timeout_seconds` | `ASSISTANT_LLM_TIMEOUT` |
| 输出上限 | `max_tokens` | `ASSISTANT_LLM_MAX_TOKENS` |

读取顺序是**逐字段数据库优先、环境变量兜底**：

- 页面保存过的非空字段覆盖 `ASSISTANT_LLM_*`（Compose 默认值也走这一层）；
- 数据库里留空的字段继续读环境变量；
- 数据库表还不存在或迁移未应用时，`llm.raw_config()` 捕获数据库错误后直接回退环境变量，首页不会因为配置表缺失白屏。

全新部署不写数据库行，直接使用 Compose 注入的 `http://ollama:11434/v1` + `qwen3:4b`；管理员在页面保存后才由数据库行覆盖。

## 四、API Key 的显示、加密与清除

页面**不回显**已保存的 Key：

- 输入框永远为空；
- 已存在 Key 时，字段下方提示“已保存一个 API Key”；
- 留空保存 = 保持原值；
- 勾选「清除已保存的 API Key」再保存 = 写入空字符串。

写入数据库前由 `plugins/assistant/crypto.py` 加密，格式 `enc:v1:<nonce>.<ciphertext>.<tag>`：以 `SECRET_KEY` 派生主密钥，HMAC-SHA256 生成密钥流做异或，再对 nonce + 密文做认证。读取时校验标签后解密；旧明文行原样读取，下次保存自动转密文。

边界：这是应用层字段加密，不是 KMS；能同时拿到数据库和 `SECRET_KEY` 的人仍可解密。**轮换 `SECRET_KEY` 后旧密文无法解开**，需要在配置页重新填写 API Key。

## 五、测试连接

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

## 六、数据流向提示

页面始终显示当前生效地址属于哪一类：

- `127.0.0.1`、`localhost`、`ollama`、`host.docker.internal`、RFC1918 私网、`.local` → 「本机 / 内网」；
- 其他 http/https 地址 → 「公网地址」，并明确提示每轮对话都会把当前用户的业务数据发送到该地址。

这条提示是硬要求：对话落库只说明历史留在本地，不代表推理也在本地。

## 七、运维口径

- 应用迁移：`python manage.py migrate assistant`；
- 查看内置模型是否就绪：`docker compose exec ollama ollama list`；
- 查看模型是否已载入内存：`docker compose exec ollama ollama ps`（预热后应看到 `qwen3:4b`，`UNTIL` 约为 30 分钟后）；
- 查看初始化日志：`docker compose logs ollama-init`（`already present` 后应跟着 `warming`；出现 `warmup skipped` 说明预热失败，但不阻断启动）；
- 查看当前生效配置（不打印 Key）：`python manage.py shell -c "from plugins.assistant import llm; print({k: v for k, v in llm.raw_config().items() if k != 'api_key'})"`；
- 回退到内置默认：把接口地址和模型名同时清空后保存，会删除数据库单例行（含已保存的 Key），下次请求重新读 Compose 的 `http://ollama:11434/v1` + `qwen3:4b`；也可以在 shell 里删除该行；
- 容器部署后如果只重建、不迁移，配置表不存在，读取会自动回退环境变量，但页面保存会失败；重建后必须执行迁移。

## 八、当前边界

- 只支持 OpenAI 兼容的 `/chat/completions`，不接 Anthropic / Gemini 原生协议；
- 不做模型列表拉取，模型名手工填；
- 不做多配置档案 / 按用户切换；
- 内置 Ollama 是独立容器 + 模型卷，不把权重打进 Web 镜像；首次启动仍需联网拉取；
- 探测是单次请求，不代表并发、长上下文或工具调用稳定性；
- 4B 验收仍以 `docs/ai-assistant-eval.md` 的 20 条固定问句为准，配置页通过不等于验收通过。
