---
status: accepted
---

# v0.1 Skill 生命周期与职责边界

Akira Knowledge v0.1 按用户意图与知识生命周期组织 Skill，而不是按材料记录、知识资产、关系记录等领域对象机械一一拆分。产品自身包含一个总路由 `akira-knowledge` 与四个领域 Skill：`knowledge-capture` 负责低摩擦捕获并建立材料记录；`knowledge-curate` 负责整理、提炼、综合以及经用户批准后创建或实质修改知识资产；`knowledge-retrieve` 负责执行 Retrieval Contract，并对 Authority 保持只读；`knowledge-maintain` 负责回顾、更新、冲突候选、陈旧内容与长期维护。综合、建立关系、回顾、更新等当前属于这些工作流内的行为，不单独拆成 Skill。Skill 拥有行为契约，不拥有领域对象。

`akira-knowledge` 只负责识别用户意图、选择子 Skill、检查必要前置条件与停止边界，不复制专业工作流。它是主要用户入口；四个领域 Skill 主要作为模型路由目标，技术上可被直接调用，但产品不要求用户记忆其名称。跨 Skill 的 Authority、修改治理、round-trip safety、检索与关系规则继续保持单一公共 source of truth，不新增 `knowledge-governance` 之类重复规则的 Skill。

Akira Knowledge 不创建自有 `knowledge-obsidian` 底层 Skill。需要 Obsidian Flavored Markdown、Bases、JSON Canvas 与 Obsidian CLI 等通用能力时，`akira-knowledge` 或 owning 领域 Skill 只声明应复用 `kepano/obsidian-skills` 中相应 Skill，不在 Router 内实现安装、加载、版本管理或能力部署；这些由实际执行任务的 Agent 按当前 Skill 管理规则处理。v0.1 常用能力至少包括 `obsidian-markdown`、`obsidian-bases` 与 `obsidian-cli`，`json-canvas` 仅在实际需要 Canvas 时按需使用，网页抽取等与 Obsidian 知识操作无关的上游 Skill 不自动成为依赖。Akira Knowledge 负责决定为什么操作、何时操作以及要实现的知识语义，上游 Obsidian Skill 负责相应格式与工具原语。对可能随 Obsidian 版本变化的 CLI 字面量，当前 `obsidian --help` 与 Obsidian 官方文档是执行时权威，上游 Skill 作为操作指导而不是永久命令真相。只有后续确认上游能力存在明显且持续的问题时，才另开决策讨论是否自建对应能力，不因局部漂移预先 fork 或复制整套上游 Skill。

机器可视化 Markdown Projection 的语义内容由 `knowledge-curate` 或 `knowledge-maintain` 等领域工作流决定，再复用上游 `obsidian-markdown` / `obsidian-cli` 等能力生成或重建；底层 Obsidian 能力不得自行推断新的 Knowledge 语义或把 Projection 提升为 Authority。
