# v0.7.0 — 三档模型智能路由 + 新手可用性修复

**2026-09-18**

## 新功能

- **三档模型智能路由** (`forge/routing.py`)：SmartRouter 子类，零契约改动，任务级选档。
  - `economy`：按有效单价升序，仅可重试失败才上浮
  - `balanced`：中端主力档首发，失败向上升级（默认）
  - `premium`：两阶段流水——中端出草稿 → 高端集成裁决，集成段失败降级回草稿（草稿不弃）

## 文档修复

- README 第一屏标题从 `forge` 改为 `pledge-evolving`
- README 目录结构从 `agent-forge/` 改为 `pledge-evolving/`
- 新增「快速开始」前置区块，直接说明仓库名 ≠ 包名
- 新增「第一次跑真实任务」章节（API Key → 环境变量 → 首条任务）
- 修复 `run.py` 说明段落的 `python -m forge.cli` 调用说明

## 已知引入

- `read_only` 仍为声明而非强制（WB-P2 授权缺口）；当前 toolhost 未被运行时挂载，影响有限
- premium 两阶段将草稿与原始任务发送给集成裁决档（知情使用）
