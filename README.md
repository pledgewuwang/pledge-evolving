# pledge-evolving

**一个能跑的统一智能体框架。** 不是 PPT，不是概念图，是代码。

## 它解决什么问题

你可能用过 OpenClaw、Claude Code、DeepSeek Harness、WorkBuddy……每个框架都有好设计，但各自为政，互不相通。pledge-evolving 把它们各自的精华**收敛成一个内核**：

- **OpenClaw** 的系统提示分层 + 会话日志
- **Hermes** 的自我进化（curator + checkpoints）
- **DeepSeek Harness** 的配置补丁层
- **CodeBuddy** 的工具延迟加载 + 类型化记忆
- **Codex** 的影子快照回滚
- **OpenCode** 的 provider 抽象 + 降级链

## 快速开始

```bash
# 1. 配置 API 密钥（交互式向导）
python run.py setup

# 2. 跑一个任务
python run.py run "帮我总结一下 README"

# 3. 检查配置
python run.py doctor
```

**没有依赖**——纯 Python 标准库，3.10+ 即可。

## 核心能力

| 能力 | 说明 |
|---|---|
| **三档智能路由** | economy（省钱）/ balanced（推荐）/ premium（高质量），任务级自动选档 |
| **配置补丁层** | bundle → user patch → overlay，后写覆盖前写，配置永远不会锁死 |
| **影子快照** | 每次写操作前自动 git 快照，随时回滚 |
| **自我进化** | 信号抽取 → 候选生成 → 安全闸门 → 人审批 → 生效 |
| **子代理编排** | 独立上下文、深度上限、预算控制、输出去毒 |
| **协议翻译** | Anthropic ↔ OpenAI 线格式自动转换 |
| **自我测试** | `python run.py selftest` 离线跑全套检查，无需 API Key |

## 桌面 GUI

```bash
python forge_gui.py    # 打开图形界面（零依赖，纯 tkinter）
```

跨平台支持 Windows / macOS / Linux，Catppuccin 暗色主题。

## 安全设计

- deny 规则永远最高优先级
- 子代理权限被父会话天花板钳制
- `doctor` 扫描内联密钥并告警
- 用户配置可整层摘除（`dump-default-config` 恢复路径）

## 目录结构

```
forge/
├── config.py       配置合成（空根 + 补丁层）
├── policy.py       权限裁决（二维模式 + 沙箱）
├── model.py        provider 抽象 + 降级链
├── routing.py      三档智能路由
├── loop.py         agent 主循环 + 子代理
├── evolution.py    自我进化引擎
├── federation.py   异构 worker 联邦
├── checkpoint.py   影子快照
├── memory.py       类型化记忆
├── session.py      事件日志
├── wire.py         协议翻译
├── gateway.py      本地 API 网关
└── cli.py          命令行入口
```

## 许可证

MIT
