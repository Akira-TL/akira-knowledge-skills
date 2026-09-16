---
status: accepted
---

# Knowledge Authority 持久化布局约束

Akira Knowledge 0.x 系列把长期人类可读知识正文直接保存在 Obsidian Markdown 中，并把 Markdown 正文视为该人类内容 Authority；SQLite、索引或其他机器存储不得维护第二份可独立编辑的正文真相。真正进入 Knowledge 工作流的材料记录默认也具有可在 Obsidian 中阅读与链接的 Markdown 节点，而原始 PDF、网页、文件或其他 Source artifact 保持其原 owner 与原始身份，材料节点只承载 Knowledge 自己的 capture / workflow 语义与必要引用。

YAML frontmatter / Obsidian Properties 只承担适合与单篇 Markdown 共同存在的小型、原子属性，例如稳定 identity、对象类别、标题 / aliases、用户标签，以及经字段 ownership 明确定义的少量对象状态或引用。frontmatter 不承担大段 provenance、全量 typed relation、长期 revision history、embedding、graph cache 或其他高密度机器状态。具体字段名和字段分配由后续 Spec 定义，但同一逻辑字段只能有一个 Authority；其他存储中的同值只能作为 Projection。

跨对象并需要可靠机器查询的结构化 Authority 默认进入一个本地 SQLite machine store，包括 typed relation、provenance / derivation lineage、语义 history / revision metadata、必要审计及其他明确属于结构化 Authority 的机器语义。SQLite 不拥有知识正文，也不把 Markdown 退化成数据库渲染结果。0.x 默认不为每篇 Markdown 建立配套 `.json` / `.yaml` sidecar，以避免文件配对、rename、丢失与双写同步问题；只有未来某类 artifact 出现独立且充分理由时才另行决策。

Obsidian Bases、全文索引、embedding、graph cache、ranking 以及为了 Obsidian Graph View 生成的机器 Markdown 节点均属于可重建 Projection。机器可视化 Markdown 应位于明确的 generated / Projection 区域，并允许整批删除后从 Authority 重建。Git 可以作为 backup、diff、recovery 与仓库 history 基础设施，但不作为 Knowledge 领域 revision/history 的唯一 Authority。

本 ADR 只冻结持久化 ownership 和表示职责，不冻结具体目录名、SQLite 文件路径、schema、字段名、表结构或 migration 机制；这些由后续版本规划和 Spec 在不改变上述 Authority / Projection 边界的前提下确定。
