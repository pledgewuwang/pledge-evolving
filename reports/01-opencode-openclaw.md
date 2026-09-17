# OpenCode + OpenClaw 智能体框架解剖

## 1. 形态与定位
OpenCode 侧定位为**模型/provider 抽象层**：`opencode.jsonc` 用 `provider` 数组声明多个后端，每个后端带 `npm` 适配器（`@ai-sdk/openai-compatible`、`@ai-sdk/anthropic`）、`options.baseURL`/`apiKey` 与 `models` 映射，并用顶层 `model` 与 `small_model` 做「主模型 / 轻量模型」分工（`opencode.jsonc` 第 3-4 行）。OpenClaw 侧定位为**自托管的单体嵌入式 agent runtime**：一个 Gateway 进程托管一个或多个 agent，每个 agent 拥有独立 workspace、`agentDir` 状态目录和 session 存储（`openclaw-agent.md`「Workspace」「Runtime boundaries」；`openclaw-multi-agent.md`「What is one agent」）。二者可理解为「provider 抽象层」与「agent 运行时/编排层」的互补。

## 2. 主循环与运行时分層
主循环是「intake → 上下文组装 → 模型推理 → 工具执行 → 流式回复 → 持久化」的完整链路（`openclaw-agent-loop.md` 开篇）。关键分层：
- **入口**：Gateway RPC `agent`/`agent.wait`、CLI `agent`；`agent` 先校验参数、解析 session 并立即返回 `{ runId, acceptedAt }`，实现「受理与执行解耦」（同文件「Entry points」「How it works」）。
- **执行**：`runEmbeddedAgent` 负责串行化、模型/auth 解析、事件订阅、超时中止（同文件第 3 步）。
- **事件通道**：`subscribeEmbeddedAgentSession` 把 runtime 事件桥接为 `tool` / `assistant` / `lifecycle` 三类流（第 4 步）。
- **双通道**：CLI 与 Gateway RPC 共用同一 runtime；聊天通道把 delta 缓冲为 `delta`，在 lifecycle end/error 时发 `final`（「Chat channel handling」）。TUI/headless 共用事件的模式清晰。

## 3. 工具与权限模型
- **工具分级**：核心工具 read/exec/edit/write 始终可用但受 tool policy 约束；`apply_patch` 由 `tools.exec.applyPatch` 开关（`openclaw-agent.md`「Built-in tools」）。`TOOLS.md` 只写用法建议，不控制工具存在性。
- **按 agent 授权**：`agents.list[].tools.allow/deny` 可对单个 agent 收紧（如 family agent 只留 `read`、deny `write/edit/apply_patch/exec`），配合 `sandbox.mode/scope/docker.setupCommand`（`openclaw-multi-agent.md`「Per-agent sandbox and tool configuration」「Family agent」）。
- **沙箱**：workspace 是默认 cwd 而非硬沙箱，绝对路径可越界，需显式启用沙箱（同文件 Workspace note）。
- **硬/软分离**：系统提示中的 Safety 只是建议，真正强制依赖 tool policy、exec approvals、沙箱、channel allowlist（`openclaw-system-prompt.md`「Safety」末段）。

## 4. 上下文与记忆工程
- **压缩触发**：接近上下文上限或模型返回 overflow 错误（识别 `request_too_large`、`context length exceeded` 等签名）时自动压缩并重试；保留 tool_call/toolResult 配对，边界不切在工具块中间（`openclaw-compaction.md`「How it works」「Auto-compaction」）。
- **压缩可配置**：`compaction.model` 指定专用摘要模型、`keepRecentTokens` 保留近端、`identifierPolicy` 保留不透明标识符、`maxActiveTranscriptBytes` 字节护栏、`truncateAfterCompaction` 生成后继 transcript（同文件「Configuration」）。
- **会话持久化**：transcript 为 JSONL，写入受文件级 session write lock 保护（`openclaw-agent-loop.md`「Queueing + concurrency」）。
- **规则文件加载**：AGENTS.md/SOUL.md/TOOLS.md/IDENTITY.md/USER.md/HEARTBEAT.md/MEMORY.md 按生命周期路由注入，单文件上限 `bootstrapMaxChars`、总量 `bootstrapTotalMaxChars`（`openclaw-system-prompt.md`「Workspace bootstrap injection」）。
- **skills 注入**：只注入含路径与内容版 `<version>` 的精简清单，模型按需 `read` SKILL.md，预算由 `skills.limits.maxSkillsPromptChars` 控制（同文件「Skills」）。
- **记忆体系**：`MEMORY.md`（长期、启动加载）+ `memory/YYYY-MM-DD.md`（每日、按需检索）+ `DREAMS.md`（可选），配 `memory_search`/`memory_get` 工具与 dreaming 后台固化（`openclaw-memory.md`）。

## 5. 扩展生态
- **provider/模型抽象**：`opencode.jsonc` 的 provider+model+small_model 结构，天然支持多厂商混用与「廉价模型干杂活」。
- **插件与槽位**：OpenClaw 以 `plugins.slots.contextEngine`/`slots.memory` 选择实现，安装即插即用，卸载自动回落默认（`openclaw-context-engine.md`「Configuration reference」）。
- **MCP**：evidence 未涉及，标注（自述知识）。
- **自定义 agent**：`agents.list[]` 声明多 persona，各带 workspace/model/tools/sandbox。
- **命令**：`/new`、`/reset`、`/compact`、`/queue` 等斜杠命令与 CLI（`openclaw-compaction.md`、`openclaw-agent.md`「Steering while streaming」）。

## 6. 子代理与多智能体编排
- **子代理生命周期**：context engine 暴露 `prepareSubagentSpawn`/`onSubagentEnded`，支持 `isolated` 或 `fork` 上下文模式；`lightContext` 子代理跳过预 spawn 钩子以保持轻量（`openclaw-context-engine.md`「Subagent lifecycle」）。
- **sub-agent prompt 瘦身**：`promptMode=minimal` 省略记忆召回、自更新等章节，只保留 AGENTS.md/TOOLS.md（`openclaw-system-prompt.md`「Prompt modes」「Sub-agent sessions」）。
- **多 agent 路由**：bindings 确定性、**most-specific wins**（peer → parentPeer → guildId+roles → … → 默认 agent），同层按配置顺序取首个（`openclaw-multi-agent.md`「Routing rules」）。
- **推式完成**：子代理完成是 push-based，自动回报请求方，提示词明确禁止轮询 `subagents list`（`openclaw-system-prompt.md` Tooling 段）。

## 7. 最值得抄的 6 个设计
1. **系统提示分层 + 缓存边界**。要点：稳定内容（Project Context）置于缓存边界之上，易变章节（Messaging/Voice/Group Chat/Heartbeat/Runtime）置于其下，并分 `buildAgentSystemPrompt`（纯渲染）/`resolveConfig`/runtime adapter 三层。解决问题：前缀缓存复用、导出/调试面与实跑一致。机制：`systemPromptAddition`、stable prefix/dynamic suffix。移植成本：低。
2. **可插拔上下文引擎**。要点：`ingest/assemble/compact/afterTurn` 四阶段接口 + `ownsCompaction` 语义 + `hostRequirements` 能力声明。解决问题：上下文策略可替换且不锁死内核。机制：`registerContextEngine`，失败即 quarantine 并降级 `legacy`。移植成本：中。
3. **压缩前记忆落盘（memory flush）**。要点：压缩前跑一个静默 turn 把重要上下文写入记忆文件，且可指定本地小模型执行。解决问题：摘要造成信息不可逆丢失。机制：`compaction.memoryFlush.model`。移植成本：低。
4. **会话级串行队列 + 文件写锁**。要点：per-session lane（可选 global lane）串行化 run，transcript 加进程感知的文件锁（默认 60s 超时，非重入需显式 `allowReentrant`）。解决问题：工具/历史竞态。机制：队列模式 steer/followup/collect/interrupt。移植成本：中。
5. **贯穿生命周期的钩子体系**。要点：`before_model_resolve`/`before_prompt_build`/`before_tool_call`/`tool_result_persist`/`before_compaction`/`message_sending` 等，且 `{block:true}` 终止、`{block:false}` 不清除既有阻断。解决问题：不改内核即可注入/拦截/审计。移植成本：中。
6. **声明式多 agent 路由与隔离**。要点：agent=workspace+agentDir+session store 三位一体，bindings 最具体优先，per-agent tools/sandbox/model。解决问题：一进程多 persona、多账号、权限边界。机制：`~/.openclaw/agents/<id>/` 目录隔离 + `agents.list[]`。移植成本：中。

## 8. 明确短板与风险
- **凭证明文**：`opencode.jsonc` 直接内嵌 `apiKey`，evidence 文件即泄露面，应改为环境变量/密钥管理（`opencode.jsonc`）。
- **沙箱非默认**：workspace 非硬沙箱，绝对路径可越界，安全依赖额外配置（`openclaw-multi-agent.md` Workspace note）。
- **提示词护栏非强制**：Safety 章节仅为建议，operator 可整体关闭（`openclaw-system-prompt.md` Safety 末段）。
- **配置面极宽**：压缩、context engine、记忆后端、路由、钩子交叉，学习与运维成本高，易配错（多文件 configuration 小节）。
- **插件故障面**：引擎/provider 异常虽可降级，但静默降级可能掩盖问题，需依赖 doctor/日志（`openclaw-context-engine.md`「Failure isolation」）。
- **超时语义复杂**：模型 idle watchdog、provider HTTP timeout、agent 总超时相互叠加，调试困难（`openclaw-agent-loop.md`「Timeouts」）。

## 9. 对「自研统一智能体框架」的具体建议
1. **Provider 层照抄 OpenCode 结构**：`provider[] + model + small_model`，适配器用统一 interface，密钥走环境变量而非配置文件。
2. **主循环强制「受理-执行」解耦**：入口立即返回 `runId`，长任务异步推进，事件流统一为 lifecycle/assistant/tool 三类。
3. **会话串行 + 文件写锁作为默认**，把竞态防护做成框架能力而非使用方责任。
4. **上下文引擎抽象为四阶段接口**（ingest/assemble/compact/afterTurn），并支持 `ownsCompaction`，避免压缩逻辑焊死。
5. **压缩前必做 memory flush**，允许指定廉价/本地模型执行，降低信息损失。
6. **系统提示分层并显式标注缓存边界**，稳定前缀与动态后缀分离，便于前缀缓存与快照测试。
7. **钩子先于插件**：先落地 `before_model_resolve`/`before_prompt_build`/`before_tool_call`/`tool_result_persist` 四个最小钩子，再谈插件市场。
8. **权限分级 + 沙箱默认开启**：read-only 与 edit 工具分级，tool allow/deny 按 agent 声明，sandbox 作为可配置但推荐的默认项。

（报告完）
