---
status: accepted
---

# Obsidian 作为 v0.1 唯一用户前端

Akira Knowledge v0.1 只支持 Obsidian 作为用户前端与知识浏览环境，不在本版本设计第二套前端或通用可替换前端抽象。Knowledge Skill 仍以领域操作表达读取、修改、移动、重命名、属性维护、链接检查与视图查询，不把 Obsidian CLI 命令本身暴露为领域 API。依赖 Vault 语义的操作优先使用官方 Obsidian CLI；不依赖 Obsidian 特有语义且能够满足 round-trip safety 的操作可以直接修改本地文件。CLI 不可用时，只有存在经过验证的语义等价 fallback 才继续执行，否则 fail closed。Obsidian Bases 属于 Projection / UI view；MCP 与 Community Plugin 仅作为可选调用或增强层，不拥有 canonical knowledge。

为了让机器层内容也进入用户可观察的知识网络，Agent / 机器内容可以生成 Obsidian 可见的 Markdown Projection 节点，并通过 wikilink 连接到人类可读知识资产或其他可视化节点。这样形成的 Graph View 连接用于可视化和导航，不会因为“出现在图中”而把机器 Projection 自动升级为知识资产、人类内容 Authority 或正式 typed relation。canonical 内容继续优先采用普通本地文件与可检查结构，是为了数据可控、可恢复和 Agent 安全操作，而不是为了在 v0.1 同时支持其他前端。