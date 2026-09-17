# forge v1 代码审查与 v2 集成建议

## 1. 总体判断

这套框架的集成质量显著高于"七套框架的功能拼接"，设计自洽度高。最值得肯定的三处：

1. **配置合成的"空根 + 有序补丁层"**（`config.py`）：整行替换不深合并、`dump-default` 恢复通道，这两条一起堵住了"配置写坏锁死启动"的最常见故障模式。

2. **权限二维模型 + 子代理天花板钳制**（`policy.py`）：mode 管基线、规则管例外、deny 恒胜、子代理 mode 被 `clamp_to` 限死——这四条组合在一起，比七套原始框架中任何一套都更难绕过。

3. **会话作为追加式事件日志 + 派生状态可重建**（`session.py`）：日志是事实、索引是缓存，版本漂移即重建。这是真正吸收了 Codex "rollout as source of truth" 的精髓，且比 CodeBuddy 的三套状态目录干净一个数量级。

---

## 2. 具体缺陷

| # | 文件 | 弱点 | 触发条件 | 后果 | 修法 |
|---|------|------|----------|------|------|
| 1 | `config.py:68` | `_eval_expr` 用 `eval()`，虽禁了 `__builtins__` 但未禁 `__subclasses__`/`__import__` | 配置层写入 `{"$expr": "().__class__.__bases__[0].__subclasses__()..."}` | 沙箱逃逸（推测，需实测 Python 3.10+ 的限制是否足够） | 改用 `ast.literal_eval` 或白名单函数表；或至少加长度/复杂度上限 |
| 2 | `tools.py:254` | `shell_exec` 用 `shell=True`，黑名单总有绕过空间 | `forbidden_programs` 未覆盖的变体（如 `pwsh`、`bash -c`） | 命令注入导致沙箱失效 | 生产环境默认禁用 `shell_exec`；或改用 `shlex.split` + `shell=False` |
| 3 | `memory.py:80-96` | `save()` 无文件锁，原子 swap 只防半写不防竞态 | 两个进程同时 `remember()` | 条目丢失（后写的覆盖先写的） | 加 `fcntl.flock`（Unix）或 `msvcrt.locking`（Windows）；或用 `.tmp` + rename 做乐观锁 |
| 4 | `loop.py:182` | 子代理共享父代理的 `registry` 实例，`_activated` 集合是共享的 | 子代理调用 `tool_search` 激活工具 | 父代理可见工具表被污染（子代理激活的工具对父代理也可见） | 子代理应深拷贝 registry 或维护独立的 `_activated` |
| 5 | `checkpoint.py:101-106` | `rollback` 直接 `checkout` 到目标 commit，不保留当前状态 | 用户误操作回滚到错误版本 | 当前状态丢失，无法二次回滚 | 回滚前先自动 `snapshot("pre-rollback")` |
| 6 | `loop.py:279-282` | `sanitise_child_output` 只过滤 `<system-reminder>` 等显式标签 | 子代理用 `SYSTEM:` 前缀、XML 变体、Unicode 同形字注入 | 提示词注入（子代理欺骗父代理执行非预期操作） | 扩充正则覆盖 `SYSTEM:`、`[INST]`、`<<SYS>>` 等常见格式；或改为白名单只保留纯文本 |
| 7 | `session.py:91-103` | `_write_line` 在 `append()` 中重新打开文件写入，与 `_fh` 双通道并存 | `_fh` 为 None 时调用 `append()` | 重复打开文件句柄（虽不致命但浪费） | 统一为 `_fh` 通道，`_write_line` 仅在 `open()` 前的初始化使用 |

---

## 3. 边界与不变量检查

**真正被代码强制的（硬保证）：**
- deny 恒胜：`policy.py:155-160` 显式 deny 检查在所有其他判断之前
- 子代理天花板：`policy.py:46-47` 的 `clamp_to` 在 `_spawn_handler` 中被调用
- 沙箱路径拦截：`policy.py:55-64` 的 `allows_write` 对 `WRITE_TOOLS` 工具逐路径检查
- 命令黑名单：`policy.py:228-236` 的 `_command_denied` 先于模式判断

**只是文档承诺或有漏洞的（纸面约束）：**
- "密钥不进配置文件"：`doctor` 只报告警，不阻断启动；`--key` 参数仍可传入内联密钥（`cli.py:237`）
- "归档而非删除"：`MemoryStore` 的 `curate` 确实只设 `archived` 标志，但代码没有禁止直接操作 `entries` 列表删除条目
- "用户层可整层摘除"：需要显式传 `--no-user-layer` 或 `include_user_layer=False`，不是自动触发的
- "派生状态可重建"：`SessionIndex` 确实可 rebuild，但无自动触发机制，需要用户执行 `sessions --rebuild`

---

## 4. 自我迭代进化模块的集成风险

Agent 改写自己的知识/配置/提示词时，以下位置会失守：

1. **`_eval_expr`（config.py:68）**：如果 agent 能写入配置层，表达式注入等于代码执行。当前沙箱不拦配置文件写入（因为 `write_file` 只检查路径，不检查文件名模式）。

2. **`system_prompt` 拼接（loop.py:121-142）**：`extra_system` 参数无校验、无签名。如果 agent 能写入某个被拼接的文件（如 capabilities 的 `SKILL.md`），等于注入系统指令。

3. **`MemoryStore` 无完整性保护**：agent 可直接写 `MEMORY.md` 文件绕过 `remember()` API，植入恶意记忆条目，后续 `context_slice` 会注入到系统提示中。

4. **`Capability.trusted` 一旦 `trust()` 后无撤销审计**：agent 可提升自己创建的能力的信任等级，然后执行被信任的能力。

5. **子代理输出去毒（`sanitise_child_output`）只做正则替换**：agent 可以构造绕过正则的注入（如使用全角字符、HTML 实体、Markdown 注释等）。

---

## 5. 异构联邦模块的集成风险

1. **外部进程认证缺失**：gateway 没有 mTLS 或 token 认证，任何能访问端口的进程都能发请求。联邦场景下，恶意节点可以冒充合法 agent。

2. **工具输入输出清洗不足**：`tool_call` 的 `args` 直接传给 handler，`result.content` 直接返回给模型。外部 agent 可以在 `result` 中注入提示词（提示词注入的第二条路径，绕过 `sanitise_child_output`）。

3. **权限天花板无法传递给外部进程**：`Policy.child()` 只能在本进程内钳制子代理 mode。外部联邦 agent 是独立进程，本框架的权限模型对它完全无效。

4. **`ModelRouter` 无资源隔离**：联邦场景下多个 agent 共享一个 router，没有 per-agent 的 token 预算或请求限流，一个 agent 可以耗尽所有 provider 配额。

5. **Session 日志是本地文件**：联邦 agent 的交互无法追加到本机日志，导致审计链断裂。

---

## 6. 测试盲区

101 项自检覆盖了：配置合成、权限裁决、工具延迟加载、能力信任、记忆双写、会话回放、影子快照、模型降级、协议网关、子代理编排、wire 翻译。

**没覆盖的：**
- 多进程并发写入（`memory.py` 的竞态条件）
- 恶意输入对抗（prompt injection via tool result、配置层注入表达式）
- checkpoint 回滚后的会话一致性（回滚后 session 日志与文件状态不匹配）
- gateway 的并发请求处理（自检是单线程顺序测试）
- 模型降级链的退避间隔验证（`time.sleep(min(0.5 * (2 ** attempt), 4.0))` 的实际行为）

**最该补的 5 条断言：**
1. 并发 `remember()` 无条目丢失（多线程写入后 recall 数量正确）
2. `sanitise_child_output` 能挡住 `SYSTEM:`、`[INST]`、`<<SYS>>` 三种变体
3. `_eval_expr` 对 `().__class__.__bases__` 等逃逸字符串抛出 `ConfigError`
4. `rollback` 后自动产生一个 `pre-rollback` checkpoint
5. 子代理调用 `tool_search` 后不影响父代理的 `registry.names()` 结果

---

## 7. 优先级修复清单

| 优先级 | 修复项 | 工作量 |
|--------|--------|--------|
| P0 | `_eval_expr` 改用白名单函数表或加复杂度上限，阻断配置层代码执行 | 0.5 天 |
| P0 | `MemoryStore.save()` 加文件锁，防多进程竞态丢数据 | 0.5 天 |
| P1 | 子代理深拷贝 registry 的 `_activated` 集合，避免工具激活污染 | 0.5 天 |
| P1 | `sanitise_child_output` 正则扩充覆盖 `SYSTEM:`、`[INST]`、`<<SYS>>`、全角字符 | 1 天 |
| P1 | `rollback()` 前自动 `snapshot("pre-rollback")` | 0.5 天 |
| P2 | `HttpTransport` 加连接池（`urllib3` 替代或 `http.client` 复用）+ 指数退避 | 2 天 |
| P2 | `shell_exec` 生产环境默认禁用或改用 `shell=False` | 1 天 |
| P2 | `session.py` 统一双通道写入为 `_fh` 单一路径 | 0.5 天 |
