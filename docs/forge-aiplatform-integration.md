# AI Platform × Forge 集成指南

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                  AI Platform                     │
│  ┌─────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  Chat UI │→│ Chat API  │→│  Tool System   │  │
│  └─────────┘  └──────────┘  │  ┌──────────┐ │  │
│                              │  │forge_run │ │  │
│                              │  │forge_stat│ │  │
│                              │  └────┬─────┘ │  │
│                              └───────┼───────┘  │
└──────────────────────────────────────┼──────────┘
                                       │ HTTP
                                       ▼
┌──────────────────────────────────────────────────┐
│            Forge Gateway (:8799)                  │
│  ┌────────────┐  ┌────────────┐                  │
│  │ /v1/models │  │/v1/chat/   │  → upstream LLM │
│  └────────────┘  │ completions│                  │
│                  └────────────┘                  │
│                                                   │
│  本地 CLI 直接执行：                               │
│  python run.py selftest / doctor / run "任务"     │
└──────────────────────────────────────────────────┘
```

## 两种调用方式

### 方式 1：通过 Forge Gateway（远程/本地网络）

forge 以 gateway 模式运行，暴露 OpenAI 兼容 API。AI Platform 通过 HTTP 调用。

**启动 forge gateway：**
```bash
cd pledge-evolving
python run.py gateway --upstream https://api.deepseek.com --key sk-xxx --port 8799
```

**AI Platform 配置：**
```env
# .env.local
FORGE_GATEWAY_URL=http://127.0.0.1:8799
```

**用户在 AI Platform 中的使用方式：**
- "帮我用 forge 跑一个 selftest"
- "用 economy 策略让 forge 总结一下 README"
- "forge 现在状态怎么样？"

### 方式 2：通过 CLI 直接执行（本机）

AI Platform 和 forge 在同一台机器上，直接调用 forge CLI。

**AI Platform 配置：**
```env
# .env.local
FORGE_HOME=/path/to/pledge-evolving
FORGE_REPO=/path/to/pledge-evolving
```

**优点：** 无需启动 gateway，零延迟
**限制：** 仅限本机，需要 Python 环境

## 集成步骤

### 1. 复制工具文件

将 `forge-integration.ts` 复制到 AI Platform 的 `src/lib/` 目录：

```bash
cp forge-integration.ts <ai-platform>/src/lib/forge-tools.ts
```

### 2. 注册工具

在 `src/lib/tools.ts` 中导入并注册：

```typescript
import { getForgeTools, isForgeTool, executeForgeTool } from "./forge-tools";

// 在 AVAILABLE_TOOLS 数组末尾追加
export const AVAILABLE_TOOLS: Tool[] = [
  ...existingTools,
  ...getForgeTools(userSettings),  // ← 添加这行（需要传入用户设置）
];
```

### 3. 修改工具执行逻辑

在 `executeTool` 函数中添加 forge 工具的路由：

```typescript
export async function executeTool(call: ToolCall, options?: ToolOptions): Promise<ToolResult> {
  // Forge 工具路由
  if (isForgeTool(call.name)) {
    return executeForgeTool(call);
  }
  // ... 原有工具执行逻辑
}
```

### 4. 前端设置面板（可选）

在 AI Platform 的设置页面添加 Forge 配置区域：

```tsx
// src/components/settings/ForgeSettings.tsx
export function ForgeSettings() {
  return (
    <div className="space-y-4">
      <h3>Forge 集成</h3>
      <div>
        <label>Gateway URL</label>
        <input
          type="text"
          placeholder="http://127.0.0.1:8799"
          // 保存到用户设置
        />
      </div>
      <p className="text-sm text-muted">
        配置后 AI 将获得 forge agent 能力，可执行复杂任务、自我测试、配置管理等。
      </p>
    </div>
  );
}
```

### 5. 部署

```bash
# 重启 AI Platform
systemctl restart aip

# 验证 forge 工具已加载
curl http://localhost:3389/api/health
```

## 使用示例

### 在 AI Platform 聊天中

```
用户：帮我检查一下 forge 的配置是否正常
AI：[调用 forge_status 工具]
    ✅ Forge gateway 在线 (http://127.0.0.1:8799)
    可用模型：deepseek-flash, mimo-v2.5
    [调用 forge_run 工具，command=doctor]
    [显示 doctor 检查结果]
```

```
用户：用 economy 策略让 forge 帮我写一首诗
AI：[调用 forge_run 工具，task="写一首关于秋天的诗"，strategy="economy"]
    [forge 执行结果]
```

### 工具互通

forge 的子代理（federation）也可以调用 AI Platform 的能力：

```
forge agent → AI Platform chat API → 获取 AI 回答 → 返回 forge
```

这形成了一个双向能力网络。

## 默认行为：用户主动选择接入

forge 工具**默认不注册**，不会出现在 AI 的工具列表中。原因：

1. **工具描述消耗 token**：每个工具的 description 会随每次请求发送给 LLM，白白浪费
2. **暴露内部细节**：forge 的架构信息不应该让用户在不知道的情况下看到
3. **按需启用**：只有用户明确选择「接入 Forge」时，forge 工具才生效

用户在 AI Platform 的设置页面开启「Forge 集成」开关后，forge 工具才会被注入到工具列表中。
## 安全考虑

- forge gateway 默认只监听 127.0.0.1，不暴露到外网
- AI Platform 的认证机制保护访问
- forge 自身的 policy 系统提供沙箱隔离
- API 密钥通过环境变量传递，不落盘

## 故障排查

| 问题 | 解决方案 |
|---|---|
| forge 工具不显示 | 检查 `FORGE_GATEWAY_URL` 或 `FORGE_HOME` 环境变量 |
| 连接超时 | 确认 forge gateway 已启动：`python run.py gateway ...` |
| 权限错误 | 检查 forge 的 policy 配置（`bundles/base.json`） |
| 模型不可用 | 检查 forge 的 provider 配置（`~/.forge/forge.patch.json`） |
