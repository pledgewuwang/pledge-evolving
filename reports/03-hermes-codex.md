# Hermes Agent + Codex CLI 智能体框架解剖

证据来源：本机实测。Hermes 可执行文件 `C:\Program Files\AutoClaw\resources\python\Scripts\hermes.exe`（site-packages 版本 0.19.0 dist-info，doctor 报告运行版本 0.21.1），配置目录实为 `%USERPROFILE%\AppData\Local\hermes`（config.yaml v33、state.db/cron/executions.db/projects.db 均 WAL 模式）；Codex 为 `codex.exe` CLI 0.153.4，配置 `%USERPROFILE%\.codex\config.toml`。

## 1. 两者的形态与定位差异

Hermes 顶层 argparse 一口气暴露 80+ 个子命令（chat/model/moa/fallback/gateway/proxy/lsp/cron/kanban/hooks/skills/plugins/curator/memory-graph/checkpoints/backup/acp/serve/dashboard/desktop/gui…），是一个"个人 AI 操作系统"：Python 单体（hermes_cli 目录 154 个 .py），既做终端 agent，也做消息网关、调度器、桌面应用、MCP/ACP 服务器，强调多平台、多身份（profile）、长期运行。

Codex 顶层只有 20 余个命令（exec/review/resume/fork/queue/apply/sandbox/mcp/plugin/app-server/agents/migrate-rollouts…），是 Rust 写的"专注编码任务的 agent harness"：默认进 TUI 主循环，非交互用 `codex exec`（支持 `--json`、`--output-schema`、`-o` 输出末条消息），架构围绕沙箱、审批与会话回放三件事收紧。一句话：Hermes 是平台，Codex 是工具。

## 2. Hermes 的能力矩阵（从子命令面反推）

1. 模型与推理供给域：`model`、`fallback`（限流/过载/连接错误时按链重试）、`moa`（Mixture-of-Agents 多槽位聚合，由 `/moa` 触发）、`auth`（凭据池，支持 Nous Portal/xAI/MiniMax/Codex OAuth）、`proxy`（本地 OpenAI 兼容代理，为 OAuth 提供商附加真实凭据）、`egress`（iron-proxy 出站凭据注入防火墙）、`secrets`（Bitwarden/1Password）。
2. 知识与技能域：`skills`（19 个子命令：search/install/audit/diff/list-modified/trust/publish/tap…）、`bundles`、`plugins`（capabilities 声明 vs 授予、doctor 运行时契约校验、hermes-pack.yaml 声明式打包）、`curator`（后台辅助模型审查 agent 自建技能：prune/merge/archive，带 ledger 账本与 pin 保护）、`memory`（honcho/mem0/hindsight 等 7 种外部记忆，内置 MEMORY.md/USER.md 常驻）、`memory-graph`（journey 时间线星座图，技能与记忆按时间成图）。
3. 执行与安全域：`hooks`（shell 脚本钩子 + 首次使用同意白名单 shell-hooks-allowlist.json，doctor 查 exec 位/mtime 漂移）、`approvals`（从历史挖掘允许列表提案）、`security`（OSV.dev 供应链审计 venv/plugins/MCP）、`checkpoints`（write_file/patch/terminal 前用影子 git 仓库快照工作区）、`verify`（探测项目运行配方并冒烟）、`worktree`。
4. 连接与触达域：`gateway`（Telegram/Discord/WhatsApp/Weixin，可装 systemd/launchd 服务）、whatsapp/slack/send/pairing/peer（跨机器 bot 间 DM）、webhook、`lsp`、`mcp`（客户端 + 服务端双向）、`acp`（Agent Client Protocol server）。
5. 自治与协作域：`cron`（durable executions、incidents、tick）、`kanban`（多 profile 协作板，含 decompose/specify/swarm 子模块）、`project`、`pause/resume`（一键急停调度与新回合）。
6. 形态与运维域：`profile`、`serve`/`dashboard`/`desktop`/`gui`/`console`、`computer-use`（cua-driver，doctor 输出权限矩阵）、`backup`/`import`/`import-agent`（可直接导入 Claude Code/Codex 配置）、`doctor`/`dump`/`debug`/`monitoring`/`update`/`migrate`/`claw`。
7. 自我观测域：`sessions`（SQLite + FTS5，export JSONL/Markdown/QMD，prune/archive/optimize/repair）、`insights`、`journey`、`prompt-size`、`logs`。

## 3. Hermes 的三处独特设计

1. 三层模型可靠性栈：主模型 → `fallback` 顺序链（只在限流/过载/连接错误触发）→ `moa` 多模型并行聚合。代理与凭据也分层：`proxy` 把 OAuth 令牌藏在本地端点后，`egress` 在网络出站侧注入凭据，使密钥永不进子进程环境。
2. 技能会"生长与代谢"：agent 自建技能进入 curator 管辖，带 provenance 标记；后台模型周期审查、合并、归档（只归档不自动删除，archive 可 restore），bundled/hub 技能永不触碰，用户可 pin。配合 memory-graph 把"学到的技能"与"记忆"做成随时间累积的星图，形成闭环的经验资产。
3. 影子 git 检查点 + 急停开关：`checkpoints` 在每次写/补丁/终端调用前对工作区做快照，提供 /rollback；`hermes pause` 同时冻结 cron、kanban 派发与 gateway 新回合，是少有的"agent 运行时总闸门"设计。

## 4. Codex CLI 的架构要点

TUI/exec 双前端共用一个 agent 核：无子命令时进交互 TUI，`codex exec` 面向脚本（stdin 追加为 `<stdin>` 块、`--json` 事件流、`--output-schema` 约束最终回答、`--ephemeral` 不落盘）。`app-server`（实验性）+ `agents` 命令表明其正走向常驻本地 daemon、多前端共享会话；`--remote ws://` 可把 TUI 接到远端 app server。

沙箱与审批是一等公民：`-s/--sandbox` 三档 read-only / workspace-write / danger-full-access；`--approve-for-me` 用 workspace-write 做自动审批；`codex sandbox` 可独立运行任意命令（Windows restricted token，实测 config.toml 有 `[windows] sandbox = "unelevated"`、`sandbox.2026-09-05.log` 审计日志）；`--add-dir` 扩大可写根；`shell_environment_policy.inherit = "core"` 控制环境变量继承面。还有 `--dangerously-bypass-hook-trust`、execpolicy `.rules` 文件（`--ignore-rules` 可关）。

配置分层：`~/.codex/config.toml` 为基线，`-p/--profile` 叠加 `<name>.config.toml`，`-c key=value` 点路径覆盖（值按 TOML 解析），`--strict-config` 对未知字段报错；项目级用 `[projects.'<路径>'] trust_level = "trusted"` 做信任登记。技能与插件目录约定清晰：`~/.codex/skills/` 与 `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/skills/<name>/SKILL.md`（实测 documents/pdf/browser/computer-use 等插件均以版本号目录缓存），marketplace 在 config 中以 `[marketplaces.*]` 声明（local 源）。

会话即 rollout：每次会话写 `sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl`，首行 `session_meta`（含 cwd、cli_version、model_provider、完整 base_instructions），其后是 ordinal 递增的 response_item/event_msg/task_started/world_state/turn_context 事件；另有 `session_index.jsonl` 索引、`migrate-rollouts` 迁移旧格式、`resume/fork/archive/queue` 围绕同一回放原语操作。

## 5. Codex 的三处独特设计

1. 沙箱与审批强绑定：安全不是开关而是执行路径本身——每条模型生成的命令都按沙箱策略裁决，审批提升（escalation）与 read-only/workspace-write 策略共用一套机制；独立的 `codex sandbox` 子命令使同一策略可被外部复用，审计日志按日落盘。
2. Rollout 可回放：JSONL 事件流含完整系统提示、模型响应、工具调用与环境状态，天然支持 resume/fork、`apply`（把最近一次 diff 用 git apply 落盘）、bug 复现与 `exec --json` 式机器消费；会话文件本身就是调试器。
3. 声明式覆盖与信任分层：点路径 `-c` TOML 覆盖 + `--strict-config` 防配置腐烂 + per-project trust_level，使"同一二进制在不同仓库拿到不同权限"成为显式数据而非隐式习惯；插件经 marketplace/版本目录不可变缓存，config 中逐项 `enabled = true`。

## 6. 最值得抄的 6 个设计

1. Codex 三档沙箱 + 命令级审批。解决 agent 误操作。机制：策略枚举随每次 exec 裁决，审批走同一路径，独立 sandbox 子命令复用。移植成本：中（Windows 需 restricted token，macOS seatbeat 已有模板）。
2. Codex rollout JSONL + session_meta。解决会话不可复现、难调试。机制：按日期分目录、ordinal 事件、索引文件、resume/fork/apply 建立其上。成本：低，纯约定。
3. Hermes fallback 链 + MoA。解决单点模型限流与质量不稳。机制：按错误类型（429/过载/网络）顺序重试；MoA 多槽位并行聚合。成本：中。
4. Hermes checkpoints 影子 git。解决 agent 改坏工作区。机制：写操作前向影子仓库提交，/rollback 与 prune/GC 配套。成本：低（git plumbing 即可）。
5. Hermes curator + provenance/pin/ledger。解决 agent 自建知识膨胀腐烂。机制：辅助模型后台审查，只归档不删除，bundled 资产豁免，操作入账本。成本：高（需要判定模型与状态机）。
6. 两者共同的 skills 目录约定（SKILL.md + 版本化缓存 + trust）。解决能力扩展无标准。机制：目录即插件、`skills list/audit/diff`、项目级技能需 trust（Hermes 的 `.hermes/skills` 白名单与 Codex 的 projects trust_level 异曲同工）。成本：低。

## 7. 两者共同的短板

- 状态面过宽、运维心智重：Hermes config 已 v33→v42 落后 9 版仍靠 migrate 追；80+ 子命令无导航难以穷尽。Codex 侧 `.codex` 下并存 config.toml.bak、global-state tmp 文件、三套 sqlite（logs/memories/goals/queue）与 rollout-migrations，迁移痕迹外露。
- 安全模型不对称：Codex 沙箱强但凭证管理弱（实测 ANTHROPIC_AUTH_TOKEN 明文写在 config.toml 的 shell_environment_policy.set 里）；Hermes 有 secrets/egress/hooks 同意制，却默认缺沙箱，执行安全靠审批与 checkpoints 兜底。
- 知识格式各自为政：SKILL.md 约定两家相似但不兼容，记忆（Hermes MEMORY.md/SQLite 对 Codex memories_1.sqlite）无法互通；Hermes 用 import-agent 单向导入只是缓解。
- 桌面/daemon 化仍在实验期：Codex app-server/remote-control 标 experimental；Hermes 同时维护 TUI/serve/dashboard/desktop/gui 五个前端，154 个扁平 .py 模块说明内部边界正在重构（doctor 中专门有"Sep 14 分解后移除的 import 路径"兼容检查）。

## 8. 对自研统一智能体框架的建议

1. 内核做小：一个 agent 核 + 事件流（学 Codex rollout JSONL，含 session_meta/ordinal），TUI、非交互 exec、daemon、桌面全部是该流的消费者，从第一天支持 resume/fork。
2. 安全层先行：把"沙箱策略 + 命令审批 + 项目信任登记"做成单一策略引擎，三档枚举（read-only/workspace-write/full-access），每次工具调用必经裁决，并提供独立 sandbox 子命令与按日审计日志。
3. 凭据与执行隔离：密钥只允许来自系统密钥库或本地凭证代理（学 Hermes proxy/egress），禁止进入 config 和子进程环境变量；环境继承用白名单策略。
4. 模型供给做成三级：主模型、按错误类型触发的 fallback 链、可选 MoA 聚合；统一 OpenAI 兼容 wire 层，provider 差异在适配层消化。
5. 知识层采用"目录即能力 + 元数据治理"：SKILL.md 标准目录、版本化不可变缓存、provenance 标记、项目技能需 trust；对 agent 自建知识引入 curator 式归档（只归档不删除、可 pin、操作有 ledger）。
6. 每次写操作前影子快照（git worktree/plumbing），并提供全局 pause/resume 急停，统一冻结调度与新回合。
7. 配置用分层叠加 + 严格模式：基线 TOML/YAML、profile 层、点路径 `-c` 覆盖、`--strict-config` 未知字段报错、`doctor` 内置版本漂移与数据库完整性检查（FTS5/VACUUM/WAL）。
8. 扩展面收敛为三种契约：tool（MCP 双向）、skill（声明式目录）、hook（带同意白名单与 mtime 漂移检测）；插件能力必须"声明 vs 授予"分离并过运行时 doctor，供应链审计（OSV）默认覆盖 venv 与插件。
