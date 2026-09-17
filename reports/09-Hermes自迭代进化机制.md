# Hermes 自迭代进化机制解剖

实测环境：`hermes` 实际由 `%USERPROFILE%\AppData\Local\hermes\hermes-agent` 的 v0.21.1（2026.9.7，editable 安装）提供，HERMES_HOME 为 `%USERPROFILE%\AppData\Local\hermes`；任务书所指 AutoClaw 内置 Python 站点包是 v0.19.0 旧副本，下述机制以实际运行版源码 + 实跑命令为准。

## 1. 进化闭环总览

信号 → 沉淀 → 治理 → 可视化/回滚，四条链路：

对话每一轮结束后，主 agent 可派生一个守护线程 fork（`agent/background_review.py`），回放本轮快照，回答"有没有值得记住的人/偏好（memory）"和"有没有可复用的做法/纠正（skill）"，直接用 memory 工具与 skill_manage 落盘 → 沉淀物进 `memories/MEMORY.md、USER.md`（§ 分卡）与 `skills/<skill>/SKILL.md + references/templates/scripts/`，并在 `skills/.usage.json` 留下 `created_by:"agent"` 标记与 use/view/patch 计数 → curator 每 7 天空闲时跑一次：先做无 LLM 的 active→stale(30天)→archived(90天) 确定性迁移，再（需显式开启 consolidation）派第二个 fork 把窄技能合并成 class-level 伞技能 → 每次变异追加 JSONL 账本、每次真跑前打 tar.gz 快照、journey 把技能与记忆时间化成星图、checkpoints 与账本支持两级回滚。用户显式入口是 `/learn`（`agent/learn_prompt.py`，把任意素材蒸馏成一个技能）。`hermes learning`、`hermes memory-graph` 只是 `journey` 的别名（根帮助明示 `journey (learning, memory-graph)`）。

## 2. learning 子系统的实际机制

信号来源（fork 提示词原文）：用户纠正风格/格式/啰嗦度（"stop doing X"、"remember this" 是一等信号）、纠正流程/步骤顺序、出现非平凡技术/调试/绕行方法、本次加载的技能被发现有错或缺步、用户自曝身份/偏好/期望。判定方式是 LLM 语义判断而非规则，但提示词给了硬性反模式：环境性故障（缺二进制、未配凭据）、对工具的负面断言、未解决的失败、一次性叙事一律不许沉淀；"Nothing to save" 合法但不许当默认。沉淀形态：memory 存事实卡（有字符预算，默认 MEMORY 2200 / USER 1375），技能存"始终生效的规则在 SKILL.md、偶发深度在 references/"。fork 默认继承父运行时（吃前缀缓存），可由 `auxiliary.background_review.{provider,model}` 路由到辅助模型；上限 16 轮、600k 输入 token；新用户轮次 2 秒内可取消它（前台优先）；托管本地推理场景经 idle 队列在安静 15 秒后派发、最长滞留 30 分钟强制跑。本机实测 `journey --json`：1 个 agent 技能节点 +2 张记忆卡、2 条词法连边。

## 3. curator 的实际机制

无 cron 守护，`maybe_run_curator()` 在会话启动/空闲钩子里判门：启用（默认 on）、未 pause、距上次 ≥ `interval_hours`（默认 168h）、已空闲 ≥ `min_idle_hours`（2h）；首次只播种不跑。确定性阶段：30 天无活动标 stale、90 天归档（移动到 `.archive/`，绝不删除），重新使用即复活；cron 引用的技能、pinned、受保护内置（仅 `plan`）豁免；从未用过且不足 30 天的新技能有宽限；内置技能默认也参与（`prune_builtins` 默认 true，首次见到才起钟，归档名进 `.curator_suppressed` 防升级复活），hub 技能永不参与。LLM 合并阶段默认关（`consolidate:false`，省辅助模型费用），开启后跑伞化提示词，三种手法：并入现有伞、新建伞、降级为 references/templates/scripts。模型走 `auxiliary.curator` 槽位。产物：`skills/.curator_state`、`logs/curator/<时间戳>/run.json + REPORT.md`（本机 run_count=0，处于首跑延迟态）。purge（物理删除超 `archive_ttl_days` 的归档，默认 0=禁用）只能显式执行。

## 4. memory-graph / journey 的作用

`agent/learning_graph.py` 把非 base 的"学到的"技能（`created_by=agent` 或 use_count>0）与 MEMORY/USER 卡片统一成节点：技能边取 frontmatter 声明的 `related_skills`（双端都存在才连），记忆→技能边用词元重叠打分（技能名命中加 6 分，每卡取 top4）；节点时间戳取最近活动时间，缺省退文件 mtime（记忆卡无真实逐卡时间，用 mtime+序号）。CLI 输出时间轴条形图与可回放星座（`--reveal/--play`），节点可直接 edit/delete（删技能=归档，删记忆卡=原子重写 md）。进化上的用处：让"我学会了什么、哪条记忆连着哪个技能"可审计、可人工纠错，是治理的用户界面而非新的学习引擎。

## 5. provenance 与 trust 模型

三层来源判定：bundled（`.bundled_manifest` 的 name:hash）、hub（`.hub/lock.json`）、其余本地技能；curator 可管辖权不靠目录推断，只认 `.usage.json` 里 `created_by=="agent"` 这一显式标记（前台 agent 替用户写的不算；源码注释明说该字段是"托管opt-in标志，不是作者身份证明"）。写入时由 ContextVar `skill_write_origin` 区分 `foreground` 与 `background_review`，账本 actor 由此派生为 agent/curator，CLI 操作记为 user。提升/收回信任的人工动作：`curator adopt`（用户声明把无主技能交给 curator，高 patch 数不能反推归属）、`pin/unpin`、`skills trust`（信任项目仓库内的本地技能，帮助文本实测）、组织镜像技能可编辑但删除须管理员、改动走 sync propose。

## 6. 安全边界

自动可写：fork 只能写 curator 自有的 agent 标记技能与记忆；curator fork 的 toolset 被硬限制为 `["skills"]`——没有 terminal，从构造上堵死"shell mv 绕过账本"。强制护栏（`tools/skill_manager_guards.py`，均实测源码）：read-before-write——本 fork 内必须先 skill_view 取过原文才许 patch/覆盖；consolidation 删除必须带 `absorbed_into=<已存在伞名>`，裸删 fail-closed；pinned/bundled/hub/external/无主技能对自治写入全部拒绝；rmtree 前防符号链接/junction、防越出 skills 根。人工审批：hook 首用同意，白名单 `shell-hooks-allowlist.json` 记录 `(event,command,approved_at,script_mtime_at_approval)`，非 TTY 默认不注册（也可 `--accept-hooks`/环境变量批量同意，本机即此状态）；脚本批准后被改动则 `hooks list/doctor` 报 mtime 漂移须撤销重批；阻断型事件 exit 2 + JSON `action:block` 生效，fail_closed 钩子遇垃圾输出也阻断。`prune`/批量 adopt/rollback 均有交互确认。

## 7. 回滚与可逆性

三层。归档层：archive 只是改名移动，`restore` 可逆。账本层：每次变异（任何 actor）追加 `skills/.curator_ledger.jsonl`，before/after 文件清单的内容以 sha256 去重存 blob；`rollback --ledger <id>` 先校验所有 blob 存在、校验路径不出 HERMES_HOME，先写一条 pre-rollback 安全账本再精确恢复，fail-closed。快照层：每次真跑前对整个 skills 树（含 .usage.json、.archive、.curator_state、cron/jobs.json 副本，不含 .hub）打 tar.gz，保留 5 份；整树 rollback 前再对当前树打安全快照，回滚本身也可撤销，并只改 cron 的 skills 引用字段。`hermes checkpoints` 是另一套独立机制：写文件/patch/terminal 前对工作目录用单一共享 shadow-git 裸仓快照（按项目 ref、每轮每目录一次），服务于代码任务的 /rollback，不覆盖技能进化。

## 8. 三个设计亮点

1. 确定性与 LLM 分离：便宜可解释的衰老迁移无 LLM 必跑，昂贵主观的合并默认关闭、可 dry-run 预览。
2. 工具能力收口而非提示词规劝：curator fork 根本没有 terminal，删除必须声明吸收目标，read-before-write 由代码拒绝。
3. 账本即数据集：JSONL + 内容寻址 blob 让每个变异可 grep、可单条回滚、可归责到 actor，且快照与账本互补（包完整性回填）。

## 9. 三个缺陷与治理难点

1. fail 方向不统一：background_review 配置读坏时 fail-open（默认启用、照花 token），而 pinned-guard 读不到侧车时放行删除；两处都自称 best-effort，用户难建立心智模型。
2. 过度合并激励：curator 提示词写明"归档少于 10 个就是停得太早"、迭代上限 9999、50–100 次工具调用，质量全靠 dry-run+账本兜底，沉默用户可能只在技能消失后才发现。
3. 信任凭证是自声明的：`created_by` 标记与 write-origin ContextVar 都在本地、无签名，账本也不防本机篡改（只防回滚写越界）；多实例/插件场景下归属正确性依赖所有写入方守规矩。

## 10. 给抄袭框架的实现建议

1. 一张 sidecar 表：`{id, created_by:agent|user|installed, state:active|stale|archived, pinned, use/view/patch_count+时间戳, created_at}`，原子写 + 跨进程文件锁。
2. 每个学习产物用"显式 opt-in 标记"定管辖权，禁止按目录/活跃度反推归属；提供 adopt 命令做用户显式交接。
3. 学习分三触发面：轮后语义复盘 fork、周期 curator、用户显式 /learn；复盘 fork 复用主模型吃缓存，另设辅助模型槽位与 token/迭代预算。
4. 复盘提示词内建"不许沉淀"反模式清单（环境故障、工具负面断言、未验证的失败、一次性叙事）。
5. curator 拆成无 LLM 的时间状态机 + 可选 LLM 合并两个阶段，合并输出强制结构化 YAML（consolidations/prunings），并以工具调用证据做二次核对。
6. 自治 agent 用独立最小 toolset（只给技能读写工具，不给 shell）；删除动作必须带已验证的吸收目标，否则拒绝。
7. 写前必读：用 ContextVar + 读标记集合要求 agent 在同一执行上下文先读后写。
8. 变异账本用追加式 JSONL：`{id,ts,actor,action,target,before:[{path,sha256}],after:[...]}`，内容存 sha256 blob；回滚先预检全部 blob、先存安全条目再动手。
9. 周期任务前置整树快照（含 sidecar 与调度器状态），保留 N 份，快照排除外部上游目录。
10. 外部脚本钩子实现 `(事件,命令)` 首用同意白名单 + 批准时 mtime 快照 + 漂移复检 + 阻断退出码协议。

## 11. 离线自检断言清单

1. `hermes journey --json` 能输出含 nodes/edges/stats 的 JSON，且 learning、memory-graph 是其别名。
2. skills 目录下存在 `.usage.json`，agent 自建技能记录含 `created_by:"agent"` 与三类计数。
3. `hermes curator status` 显示 ENABLED、7d/30d/90d 参数与 consolidate off。
4. `.curator_state` 含 last_run_at、paused、run_count 且首次安装不立即触发真跑。
5. curator 源码中 LLM fork 的 enabled_toolsets 恰为 `["skills"]`，无 terminal。
6. 无 absorbed_into 的自治删除路径返回 fail-closed 拒绝。
7. 技能归档只移动到 `.archive/`，全代码库不存在自动物理删除路径（purge 需显式 TTL 配置）。
8. `.curator_ledger.jsonl` 每行含 id/ts/actor/action/before/after，actor 取值仅限 curator/agent/user。
9. 账本回滚在 blob 缺失时返回失败且不改动任何文件。
10. hook 白名单条目同时含 approved_at 与 script_mtime_at_approval，`hooks doctor` 能报 mtime 漂移。
11. pinned 技能在状态迁移、LLM 合并、journey 删除三处均被豁免。
12. `hermes checkpoints status` 指向独立的 shadow-git 存储，与 skills/.curator_backups 互不重叠。
