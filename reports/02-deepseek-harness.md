# DeepSeek Harness 智能体框架解剖

## 实际读过的路径
- `%USERPROFILE%\.dsh\`：settings.yaml、cordis.patch.yml、.credentials.yaml（+bak-20260905/bak-20260912，仅比结构）、web-autostart.log（头尾+grep）、dsh_web_run.bat、dsh_web_hidden.vbs、dsh-ventus-whale\config.json
- `profiles\desktop|web|headless\`：package.json、cordis.yml、cordis.patch.yml、pnpm-workspace.yaml；`desktop\.dsh-market\state.json`
- `profiles\node_modules\@deepseek-ai\`：dsh-base\dsh-headless\dsh-web-app 的 cordis.patch.yml（各摘读）；`@dsh-external\dsh-whale-companion\`（package.json、patch、lib\index.js 前 60 行）；dsh-ventus-whale、dsh-plugin-desktop 的 package.json
- `sessions\`（4 个工作区目录、session.jsonl.zstd）、`storages\workspace.json`、`storages\session_projcache.json`
- npm 全局 `@deepseek-ai\dsh\`：package.json、lib\bin.js、lib\dump-config-*.js、lib\profile-boot-*.js、嵌套 dsh-app-boot\dsh-sandbox-local\dsh-credentials 相关 js

## 实际跑过的命令
- `Get-ChildItem` 递归枚举上述目录；`Get-Content`/`Select-String`/`grep` 读文件
- `dsh --dump-config`：经 npm shim → `cmd /c` → 直调 node.exe 三种方式均被沙箱拦截（"StandardOutputEncoding…"、"拒绝访问"）；按规则申请 `danger-full-access` 升级重试，无审批通道、失败关闭。**未获得 dump 输出**，合成顺序结论以 dump-config/profile-boot 源码为准。

## 1. 核心命题：为什么用「profile = 有序插件束补丁层」而不是单体配置
CLI 自述即答案（bin.js:77）：`boot a DeepSeek Harness profile — an ordered stack of plugin-bundle patch layers under your own overrides`。实物：每个 profile 的 cordis.yml 恒为空 `[]`（注释：树完全由补丁合成）；dsh-base 的 patch 是"ONE insert over the empty profile root"。优点：差异即配置——跨形态差异收敛到模式 bundle，用户差异收敛到 patch 层，每行配置最多存在于"一个 bundle 层 + 用户层"。

## 2. 分层模型与覆盖规则
合成顺序（dump-config 源码 + profile-boot 注释）：① 空根 cordis.yml（每次启动重写，防 loader 回写污染）；② 各 bundle 的 patch（package.json `dsh.profile.bundles` 顺序；bundle 包声明 `dsh.bundle.patch`）；③ 用户层 `profiles/<n>/cordis.patch.yml`（长驻面热重载，desktop 配 `patchReload: live`）；④ 全局层 `$DSH_HOME/cordis.patch.yml`（本机由 dsh-skin 自动管理，禁用两个皮肤）；⑤ 可重复 `--patch` overlay；⑥ 启动期生成层（如 `DSH_TELEMETRY_DISABLED` 非空即禁用，注释明言"config cannot disable a row"）。规则：按 id 寻址、后写胜；patch 替换整行 config（非深合并）；`- insert:` 插行、`disabled: true` 停用、`!!js` 惰性表达式（`process.env.DSH_TOOLS_MODE`、`dshHomePath('storages')`、`ctx.webStartup.port ?? 3080`）。行序无加载语义，激活由服务可用性驱动。

## 3. 主循环与执行形态
- **headless**：bundle 注释"mounts no Host/HTTP server/Web runtime"，`dsh --profile headless "<task>"` 一次性任务，`headlessStartup` provider + `inject`。
- **web**：webserver 行（`ctx.webStartup.port ?? 3080`）、api-gateway（dsh-host-apiproxy，"transport-agnostic dispatch face"）；`dsh.client` 行是浏览器 roster，扫进 `window.__DSH_BOOT__`；客户端插件 manifest 声明 `dsh.client.inject/platform/immediately`。
- **desktop**：dsh-plugin-desktop v2.0.5（"Electron shell composed as a…Cordis plugin"），settings 里 `dsh-desktop.*`。
- 工具/提示词挂载：每工具一插件（dsh-tool-bash/pwsh/fs/subagent/workflow…）；whale-companion 首行 `import { defineTool } from "@deepseek-ai/dsh-tools"`；persona 由 dsh-system-prompt 行配置、伴侣插件改写 `$DSH_HOME/plugins/dsh-whale-companion/persona.json`（tmp+rename 原子写）。主循环本体（dsh-agent-loop、compaction-basic、goal-round-driver、subagent 三驱动、workflow worker-thread、jobs-local）仅从包名/注入关系可见，循环内部时序未读源码（自述知识）；本会话运行环境提供的 goal/subagent/workflow/jobs 工具名与上述包一一对应，可互证。

## 4. 上下文、会话与存储
`sessions/<工作区路径消毒名>/session-<uuid>/session.jsonl.zstd`：追加式 zstd 压缩 JSONL（attachment-local 把图片字节外置、消息存 content-addressed 引用）。`storages/`：storage-json root=`!!js dshHomePath('storages')`；workspace.json（unit v2）、session_projcache.json（unit v3，每会话 rows：sessionStats/title/tokenUsage/contextPressure/contextBreakdown/todos/plan/permissions，行带 ver+seq 版本化；配置 writeEveryEvents:200/writeIntervalMs:5000）。全文检索 opt-in（session-query-sqlite `openAt: never`、`:memory:`）。遥测默认关，匿名身份存 `.anonymous-user-id`（删文件即重置）。

## 5. 扩展与插件生态
插件=npm 包；`dsh plugin --profile <n> <pnpm args>` 转发 pnpm 到 profile 目录安装。依赖支持 `github: repo#path:` 与 `file:` 本地路径（web profile 实测）。模块解析双锚点：先 dsh 安装树、再 profile 目录；`profiles/node_modules` 扁平 fallback 由 healProfilesModuleFallback 对安装闭包 BFS 逐包建 junction。市场：dshmarket/dsh-community-market + `.dsh-market/state.json`。外置伴侣插件实测三例：whale-companion（persona+近限自动续跑）、dsh-ventus-whale（three.js 桌宠）、seekmaid-pet（file: 本地包，用户层 patch 覆盖其 python 路径）。cordis/schemastery/cosmokit 命名显示其源自 Cordis/Koishi 生态（自述知识）。

## 6. 最值得抄的 6 个设计
1. **空根+补丁合成**：配置即差异，产品线/用户/命令行差异分层收敛；后写胜按 id。机制：bundle patch→用户层→--patch。移植成本：低。
2. **dump-default 恢复通道**：用户层坏掉永不锁死启动（--dump-default-config 跳过用户层，注释称其为 recovery diagnostic）。成本：低。
3. **统一行模型 + 惰性 !!js**：`{id,name,config,disabled,inject}` 一行一事实，表达式引用运行时 ctx 但 dump 不求值不启动。成本：中。
4. **双锚点解析 + 闭包 symlink fallback**：插件永不进全局树，随装随用，任何 profile 可 Node 解析所有内置包。成本：中。
5. **追加日志 + 版本化投影**：事实日志（zstd JSONL）与派生索引（projcache 带 ver/seq）分离，索引可重建、可演进。成本：低-中。
6. **Windows ACL 沙箱**（dsh-sandbox-local）：按 workspace 建 ACE 授权、每会话随机 temp 目录配独立 SID、fail-closed 撤销。成本：高。

## 7. 短板与风险（本机已踩）
- **凭证格式反复变更致启动崩溃**：bak-0905 为 `version: "1"`（字符串）+refs 映射；bak-0912 为 `version: 1`（整数）；现为扁平 key。web-autostart.log 两次崩溃原文：`credentials-local: the value for "version" in .credentials.yaml must be a string`、`the value for "refs"…must be a string`。解析失败即 fail-loud 炸掉整棵插件树，无迁移/降级。
- **Temp 目录依赖崩溃**：log 原文 `Cannot find package '@deepseek-ai/schemastery' imported from C:\Users\D442~1\AppData\Local\Temp\dsh-whale-companion\lib\index.js`——外置插件被暂存到 Temp 导入，其运行时依赖无法解析，启动即崩（日志中重复多次）。
- 凭证明文落盘（.credentials.yaml 及其 bak 均明文，含 browser-session secret）；版本漂移（全局 CLI rc.7 / profile rc.8 / 伴侣插件 pin rc.6）；本会话实测沙箱下 node/cmd 无法 spawn、dump 命令不可用；cordis.yml 需每次重写防回写污染（说明 loader 有回写风险）；外置生态依赖 git 分支与 file: 路径，可复现性弱。

## 8. 对自研统一框架的建议
1. 采用「空根 + 有序补丁层 + id 后写胜 + 可 dump/dump-default」，用户层必须可整层摘除。
2. 统一行模型 `{id,name,config,disabled,inject}`，禁止深合并语义，配置只允许惰性表达式。
3. 插件解析做双锚点 + 安装闭包 symlink fallback；**禁止**把插件暂存系统 Temp 再 import。
4. 敏感配置 schema 带 version、自动迁移旧格式；单插件失败只降级该插件，不得炸整树。
5. 会话日志 append-only + 压缩，派生索引版本化投影、可重建。
6. 工具=插件=服务，按 headless/web/desktop 裁剪 bundle，网关传输无关。
7. 提供离线、不依赖模型的 `dump-config` 类只读诊断命令。
8. 遥测默认关、非空即关、launcher 层强制，配置无权开启。
