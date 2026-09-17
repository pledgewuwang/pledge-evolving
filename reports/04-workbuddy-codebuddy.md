# WorkBuddy(CodeBuddy Code) 智能体框架解剖

## 1. 两套客户端的关系与差异

三者是同一 `@genie/agent-cli`（`cli/package.json`，发布名 `@tencent-ai/codebuddy-code` v2.137.1）在不同宿主下的数据根：

- **`~/.workbuddy`**：桌面端 WorkBuddy（Electron，`last-launch.json` v5.5.6）的完整数据根。含 `app/`（Electron 状态：`app-config.json`={locale:zh-CN}、`window-state.json`、`lockfile`、`memory/polling-lease-*.json`）、`workbuddy.db`+`-wal`+`.workbuddy-sqlite-migrations/`（0000 baseline…0009，表名 `session_plugin_context`/`session_settings`/`automation_runs`/`buddy_snapshots`/`session_thought_level`）、`storage/{device,skeleton,user-<uid>}`、`security/{<uid>/cipher, threat-database/threat-*.db 22MB}`、`binaries/{PortableGit,node,python}`、`vendor/`。
- **`~/.workbuddy-ai`**：同构，但额外有 `projects/`、`workspace/`、`traces/`、`file-tree-manifests/`，且带 `BOOTSTRAP.md`/`IDENTITY.md`/`SOUL.md`/`USER.md`——这是"可自主成型智能体"工作区形态（BOOTSTRAP 引导确立身份并写回 SOUL/USER）。
- **`~/.codebuddy`**：CLI 原生根（`codebuddy-dir.md` 定义），只有 `settings.json`（仅 `enabledPlugins`）、`projects/`、`sessions/`、`tasks/`、`traces/`、`file-history/`、`blobs/`、`local_storage/`、`shell-snapshots/`、`plugins/`、`diagnostics/`。

两套 WorkBuddy 通过 `.fallback-merged-511822d0` 记录过迁移：`source=C:\ProgramData\WorkBuddy\users\<id>\.workbuddy → target=%USERPROFILE%\.workbuddy, reason=marker-missing, by=win32-fallback-data-migration`——即"按 Windows 用户隔离的数据目录 + 回退合并"。`memory/` 文件名以 uid 前缀（`82b7cc29…_memory.md`、`e68b45c4…_memory.md`），`.workbuddy` 与 `.workbuddy-ai` 各持不同 uid。

## 2. 主循环与执行形态

`node codebuddy --help` 实测暴露 5 条通道，同一内核不同传输层：

- **交互 TUI**（默认，无参数）：`--permission-mode` 注释写明"TUI、--serve Web、ACP"共用。
- **`-p/--print` 非交互**：实测 `node codebuddy -p "say OK only" --model deepseek-v4.1-flash --output-format json` 成功返回完整会话 JSON（含 system-reminder、assistant "OK"、`sessionId`、`providerData.model=deepseek-v4.1-flash`）。配套 `--output-format text|json|stream-json`、`--input-format stream-json`、`--include-partial-messages`、`--replay-user-messages`。
- **`--serve` Web/REST**：HTTP server + Web UI + Swagger（`dist/web-ui/`，含 PWA、`sw.js`、内嵌 `docs/cn|en` 全量文档与 `search-index-*.json`），`--auth password|none`、`--port/--host`。
- **`--acp`**：Agent Client Protocol，`--acp-transport stdio|streamable-http`（依赖 `@agentclientprotocol/sdk`）。
- **后台/常驻**：`--bg/--background`、`daemon`、`ps/logs/attach/kill/respawn`，以及独立的 `cbc-prewarm`（纯 Node、零主 bundle 依赖的 IPC 客户端，秒级 `list/ping/status/activate`）。

会话落盘见 `sessions/14812.json`：`{pid, kind:"interactive", url:"http://127.0.0.1:10112", mode:"local", version:"2.137.1"}`。

## 3. 工具与权限体系

`product.json` 的 `tools` 是权威清单（约 55 项）：`Agent, Bash, PowerShell, Glob, Grep, Read, Edit, Write, NotebookEdit, WebFetch, WebSearch, TaskCreate/Get/Update/List, EnterPlanMode, ExitPlanMode, TaskStop, TaskOutput, Skill, SkillManage, AskUserQuestion, LSP, StructuredOutput, ToolSearch, DeferExecuteTool, ImageGen/ImageEdit/VideoGen, ComputerUse, TeamCreate/TeamDelete, SendMessage, SendUserMessage, EnterWorktree/LeaveWorktree, CronCreate/Delete/List, DelegateTool, WeChatReply/WeComReply, PushNotification, ReportFindings, Workflow, Monitor, REPL`。

- **白/黑名单**：`--tools`（含 `Defer(X)/NoDefer(X)` 修饰符，`""`=禁用全部）、`--allowedTools`、`--disallowedTools`；三者语义正交（暴露策略 vs 行为约束）。
- **权限分档**：`--permission-mode` 6 个字面量 `default/acceptEdits/auto/dontAsk/plan/bypassPermissions`（运行时另认 `fullAccess`），会话内 `Shift+Tab` 循环，另有 `delegate`（主代理只留协调工具）、`work`、`ignore`（子代理专用）。求值顺序 `deny > ask > bypass > mode 基线`；`dontAsk` 是"不弹框直接拒"，`auto` 只接管"最终仍 ask"的动作且 fail-closed。
- **子代理档位**：`--subagent-permission-mode`，优先级为 调用入参 > agent frontmatter > CLI > env > settings；父会话为 `auto/dontAsk` 时子代理被钳到同一 ceiling。
- **worktree**：`-w/--worktree [name]`、`--worktree-branch`、`--tmux`，配合 `EnterWorktree/LeaveWorktree`。
- **沙箱**：`.workbuddy/settings.json` 的 `sandbox.extraAllowWrite` 显式列白名单路径；`workspace/sessions/<id>/permission.json` 实测含 `forbidden_programs: [wsl.exe, wslconfig.exe, wmic.exe, sc.exe, reg.exe, schtasks.exe]`——命令级硬禁，值得抄。

## 4. 扩展生态

- **skills**：`~/.codebuddy/skills/<name>/SKILL.md`，frontmatter `name/description/allowed-tools`，支持变量占位、shell 注入、Context Fork、隐藏 skill（`user-invocable`）、skill 内 hooks。内置 `skill-skill-creator` 带 `scripts/{init_skill.py,package_skill.py,quick_validate.py}`——技能可自举。
- **plugins**：`plugin.json` 清单，可携带 skills/commands/hooks/LSP servers/默认 settings。`plugins/installed_plugins.json`（v2，逐项记录 `scope/installPath/version/installedAt`），启用态写在 `settings.json.enabledPlugins`。
- **marketplaces**：`plugins/known_marketplaces.json` 支持三种 source——`zip`（`download.codebuddy.cn/plugin-marketplace/*.zip`）、`git`（`cnb.cool/codebuddy/marketplace`）、`directory`（内置 `resources/plugins/workbuddy-builtin`）；字段含 `autoUpdate/isBuiltIn`；团队可用 `extraKnownMarketplaces` 自动分发；索引为 `.codebuddy-plugin/marketplace.json`（实测 30KB）。
- **connectors**：与 MCP 同构但产品化。`connectors-marketplace/.codebuddy-connector/connectors.json`（390KB）是官方索引，含 `auth_injection_rules`（如 `tencent-docs-dual-token`：按 `active_in` 条件注入 `Authorization`/`X-Oneid-Access-Token`）；每 uid 一份 `connectors/<uid>/{mcp.json, connector-states.json, .master.key}`；`connectors/default/mcp.json` 全是 `connector:*` streamableHttp 条目，带 `disabledTools`/`staticHeaders`。
- **channels**：`settings.json.claw.channels.wechatmp={enabled,connectionMode:"webhook"}`；`--channels plugin:name@marketplace|server:configName`；`WeChatReply/WeComReply` 工具；凭证落 `~/.codebuddy/channels/wechat/credentials.json`。
- **MCP 配置位**：全局 `~/.codebuddy/mcp.json`、项目 `.mcp.json`、`--mcp-config`、`--strict-mcp-config`。

## 5. 记忆与计划

- **记忆**：`memory/<uid>_memory.md` 采用"人读 Markdown + `<!-- RAW_JSON_START -->{uid,memoryBlock,updatedAt}`"双写，`.bak`/`.fallback.bak` 三份冗余。文档定义 4 层静态记忆（用户 `~/.codebuddy/CODEBUDDY.md`、用户 rules、项目 CODEBUDDY.md、项目 rules、`CODEBUDDY.local.md`），加 Auto Memory（`~/.codebuddy/memories/{project-id}/`、`global/`）与 **Typed Memory 4 类**（user/feedback/project/reference，YAML frontmatter）。`MEMORY.md` 前 200 行自动入上下文。`product.json` 里有专职 `memorySelector` agent（lite 模型）做记忆筛选。
- **计划**：`~/.codebuddy/plans/`（本机为空）；内核以 XML 标签 `PLAN_FILE_PATH` + `PLAN_CONTENT` 传递（dist 可见 `CommandXmlTags.PLAN_FILE_PATH`）；`plan` 模式不是只读，而是"委托进入前模式 + 额外放行本会话计划文件写入"；`interactionmode-plan` 是内置插件。
- **projects/ vs workspace/**：`projects/<cwd-slug>/<sessionId>.jsonl` 是会话转录（实测本目录下 `f8e2d3d1….jsonl` 正是上面 `-p` 命令产物）；`.workbuddy-ai` 还多 `*.file-rollback.ndjson` 与 `*.meta.json`（含 `acpConnectionId`）。`workspace/sessions/<id>/{permission.json, snapfile/}` 是工作区级运行态。
- **traces/**：OpenTelemetry 落盘，`trace_*.json` 含 `spanCount/totalTokens/modelInfo{models,callCount,totalInputTokens}`。实测一条：`totalTokens:32298, callCount:1, agentName:"cli", duration:8872`。
- 另有 `tasks/<uuid>/<n>.json`（TaskCreate 持久化：`subject/description/activeForm/status`）、`file-history/`+`/rewind` 检查点、`blobs/`（内容哈希）。

## 6. 多智能体与编排

- **subagent**：`Agent` 工具 + `builtInSubagents`（内置 `code-explorer`）+ `.codebuddy/agents/*.md`（项目 > 用户 > 插件）。frontmatter 含 `tools/model/permissionMode/skills/mcpServers/disallowedTools/effort/maxTurns/background/initialPrompt/memory`。硬约束：嵌套封顶 5 层、每会话 spawn 预算 200、子代理输出回传做"去毒"（仿冒 `<system-reminder>` 改写）。
- **teammate/Team**：`TeamCreate/TeamDelete/SendMessage/SendUserMessage` + `product.json` 的 `team-sys-prompt`/`team-lead-prompt`。Team 与 subagent 的本质区别是**成员间可直连通信**、共享任务列表、`@member`/`@all` 寻址。`--swarm` 让队友以独立进程运行（tmux 可视化）。
- **结构化输出**：`--json-schema <schema>` + `StructuredOutput` 工具。
- **模型编排**：`--model`（13 个可选项）、`--fallback-model`（仅 `-p`）、`--effort minimal…max`、`--max-turns`、per-agent 模型（`subagents.agents.<name>.model`，来源标签 `env-global/settings-project/product-default/inherit/fallback-main`）。

## 7. 最值得抄的 8 个设计

1. **权限模式 × 规则的二维模型**｜要点：mode 定基线、allow/ask/deny 定例外，`deny` 恒优先｜问题：单一开关无法兼顾安全与自动化｜机制：9 步求值链 + `auto` 分类器 fail-closed + `dontAsk` 白名单模式｜成本：中。
2. **`--subagent-permission-mode` + 父会话 ceiling**｜要点：子代理权限可独立配置但不可越过父边界｜问题：多代理越权｜机制：7 级优先级 + auto/dontAsk 钳制｜成本：低。
3. **Defer/NoDefer 工具延迟加载**｜要点：工具"暴露策略"与"行为约束"正交，`NoDefer` 恒胜｜问题：工具太多撑爆上下文｜机制：`ToolSearch` 发现 + `DeferExecuteTool` 执行，5 级合并｜成本：中。
4. **Connectors 的声明式鉴权注入**｜要点：`connectors.json` 用 `auth_injection_rules` 描述"何时/向谁/注入哪个 header"｜问题：N 个三方服务各自 OAuth 双 token｜机制：条件（`active_in`）× 模板（`${access_token}`）｜成本：中。
5. **命令级沙箱黑名单**｜要点：`permission.json.forbidden_programs` 硬禁 `wsl/wmic/sc/reg/schtasks`｜问题：绕沙箱的"系统管理后门"｜机制：Bash 执行前程序名匹配｜成本：低。
6. **内存三段式落盘**｜要点：Markdown 供人读、`RAW_JSON` 供机读、`.bak` 冗余｜问题：记忆既要可编辑又要可解析｜机制：同文件双写 + Typed Memory 4 类｜成本：低。
7. **traces 单文件带 token/span 计量**｜要点：每次 agent run 一条 `trace_*.json`，含 `totalTokens/callCount/models`｜问题：成本与延迟黑盒｜机制：OpenTelemetry span + 按 pid 分目录｜成本：低。
8. **`cbc-prewarm` 预热进程**｜要点：管理 CLI 故意不依赖主 bundle，毫秒级 IPC｜问题：冷启动慢｜机制：纯内置模块 + unix sock/named pipe，地址与主进程同构｜成本：中。

## 8. 明确短板与风险

- **状态目录三套并存**（`.workbuddy`/`.workbuddy-ai`/`.codebuddy`），uid 与 legacyOwnerUid 混用，迁移靠 `fallback.bak`/`.fallback-merged-*` 兜底——一致性维护成本高，易出现"哪份是真"。
- **`memory/*_memory.md` 的 memoryBlock 实测为空**，说明自动记忆在桌面端尚未真正产出；`plans/` 也是空目录。
- **内核与桌面强耦合**：`known_marketplaces.json` 里的 `workbuddy-builtin` 指向 `D:\HRSoftstore\Install\WorkBuddy\...`，与当前安装路径（AppData）不一致——硬编码路径脆弱。
- **工具面过大**（55 项 + `REPL`/`ComputerUse`/`Workflow`），`minimal` 模式需靠"只给 REPL + 沙箱仅 Bash/Edit"来裁剪，说明默认暴露过宽。
- **`auto` 分类器的可用性依赖模型**，长会话会退化/中止，属于外部不确定性。
- **Beta 面广**：channels、HTTP API、connectors 均为 Beta，接口漂移风险。

## 9. 对「自研统一智能体框架」的具体建议

1. **单一数据根 + 显式 schema 版本**：只保留一个 `~/.<product>/`，用 `migrations/NNNN_*.sql` + `meta` 表做版本化，禁止目录级 fallback 复制。
2. **权限内核照抄二维模型**：`mode(基线) + allow/ask/deny(例外)`，`deny` 恒优先，非交互下 `dontAsk` 为默认（不做静默 bypass）。
3. **子代理权限必须可独立配置且有 ceiling**：实现 `subagent_permission_mode` + 父会话上限钳制。
4. **工具默认延迟加载**：内置 `ToolSearch` + `DeferExecuteTool`，工具列表用 `Defer()/NoDefer()` 覆盖，`NoDefer` 优先级最高。
5. **沙箱做命令级黑名单而非仅路径白名单**：硬禁 `wsl/wmic/sc/reg/schtasks/powershell -EncodedCommand`。
6. **扩展统一为一种清单 + 三种 source**：`skill/plugin/connector` 都用 `<dir>/.<product>-plugin/manifest.json`，source 支持 `zip|git|directory`，带 `autoUpdate/isBuiltIn`。
7. **三方集成走"连接器声明 + 鉴权注入规则"**，而非在代码里写死 OAuth 分支。
8. **记忆双写 + Typed**：Markdown 人读区 + `RAW_JSON` 机读区，4 类（user/feedback/project/reference），`MEMORY.md` 只截前 200 行入上下文。
9. **可观测性内建**：每次 run 落一条含 `totalTokens/callCount/models/duration` 的 trace，按 pid 分目录，支持离线分析。
10. **通道抽象为"入站事件 → 会话 → 出站回复工具"**：`--channels` 统一 `plugin:x@market` / `server:y`，凭证按 channel 落盘，避免为每个 IM 写一套适配。
