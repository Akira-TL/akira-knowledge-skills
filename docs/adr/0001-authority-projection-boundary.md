---
status: accepted
---

# Authority 与 Projection 分离

Akira Knowledge 对每一项逻辑语义只允许一个可编辑的 Authority，并按语义职责而不是物理存储格式划分 ownership。知识资产正文，以及用户主动维护的标题、别名、标签和普通导航链接，属于人类内容 Authority；关系记录、材料记录的处理状态、provenance / derivation lineage、精确外部引用，以及后续明确的治理与 revision 语义，属于结构化 Authority。外部网页、文件、ContextD、Akira Research 等对象的事实与身份仍由其原 owner 持有 Authority，Knowledge 只保存必要引用和自身工作流语义。Obsidian Bases、全文索引、embedding、graph cache、ranking、generated context view 等 Projection 可以持久化，但必须能从 Authority 或明确 lineage 重建，丢失或过期不得导致 canonical knowledge 丢失。Projection 界面只有在字段明确映射到某个 Authority 字段时才能把编辑作为对该 Authority 的修改请求；模型生成的摘要、标签候选、关系候选和相似度在被相应治理规则接受前仍属于 Projection / candidate。该决策明确拒绝同一语义存在两份可编辑 Authority 的双主同步模型。
