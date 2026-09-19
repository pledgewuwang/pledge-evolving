# Forge 插件市场架构

## 设计目标

参考 DeepSeek Harness 的 bundle 生态，建立 forge 的插件市场——让社区贡献的能力模块可以被发现、安装、组合。

## 核心概念

```
forge/
├── bundles/              ← 核心配置层（已有）
│   ├── base.json         ← 基线配置
│   └── modes/
│       └── coding.json   ← 编码模式
├── plugins/              ← 插件目录（新增）
│   ├── community/        ← 社区插件
│   │   ├── rag-memory/
│   │   ├── web-crawler/
│   │   └── code-review/
│   └── local/            ← 本地开发插件
├── capabilities/         ← 能力声明（已有，扩展）
└── plugin-registry.json  ← 插件注册表
```

## 插件格式

每个插件是一个目录，包含：

```json
// plugin.json — 插件元数据
{
  "name": "web-crawler",
  "version": "1.0.0",
  "description": "智能网页爬取，支持单页/全站/深度优先",
  "author": "community",
  "tags": ["web", "crawl", "scrape"],
  "minForgeVersion": "0.7.0",
  "entry": "main.py",
  "capabilities": ["web_crawl", "web_read"],
  "config": {
    "maxDepth": { "type": "number", "default": 3 },
    "timeout": { "type": "number", "default": 30 }
  }
}
```

```python
# main.py — 插件入口
from forge.capability import Capability

class WebCrawlCapability(Capability):
    name = "web_crawl"
    
    def execute(self, url: str, depth: int = 1) -> dict:
        """爬取网页内容"""
        # 实现...
        return {"url": url, "content": "...", "links": []}
```

## 安装流程

```bash
# 从 registry 安装
forge plugin install web-crawler

# 从本地目录安装
forge plugin install ./my-plugin/

# 从 URL 安装
forge plugin install https://github.com/user/plugin

# 列出已安装
forge plugin list

# 卸载
forge plugin uninstall web-crawler
```

## 插件注册表

```json
// plugin-registry.json
{
  "plugins": [
    {
      "name": "web-crawler",
      "version": "1.0.0",
      "description": "智能网页爬取",
      "author": "community",
      "downloads": 1234,
      "rating": 4.5,
      "url": "https://github.com/forge-plugins/web-crawler",
      "tags": ["web", "crawl"],
      "verified": true
    }
  ]
}
```

## 能力发现

AI 在执行任务时自动发现可用能力：

```python
# forge 会扫描所有已安装插件的能力
available = capability_registry.list()
# → ["web_crawl", "web_read", "code_review", "memory_recall", ...]

# 根据任务自动选择
if "爬取网页" in task:
    use("web_crawl")
if "代码审查" in task:
    use("code_review")
```

## 安全模型

1. **沙箱执行**：插件在隔离环境中运行，不能访问系统资源
2. **权限声明**：插件必须声明需要的能力，forge 按需授权
3. **签名验证**：官方插件经过签名，社区插件需用户确认
4. **超时保护**：每个插件调用有独立超时，防止挂起

## 与 DeepSeek Harness 的对比

| | DeepSeek Harness | Forge 插件市场 |
|---|---|---|
| 安装方式 | `dsh plugin add` | `forge plugin install` |
| 配置合并 | bundle overlay | 同（兼容现有 bundle） |
| 能力声明 | implicit（代码推断） | explicit（plugin.json） |
| 社区生态 | GitHub + npm | registry + GitHub |
| 安全模型 | 基本 | 沙箱 + 签名 + 超时 |
| 版本管理 | 手动 | semver + 自动检查更新 |
