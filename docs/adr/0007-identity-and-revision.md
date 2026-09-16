---
status: accepted
---

# 稳定 identity 与 revision 语义

Akira Knowledge 0.x 系列要求材料记录、知识资产与关系记录拥有独立于文件路径、文件名、标题和 Obsidian wikilink 文本的稳定机器 identity。rename、move 与普通标题修改不会创建新对象，只更新当前 locator、可读属性与对象 revision。每次 canonical Authority 成功发生变化时，对象 revision 都必须变化；Projection 重建、全文索引刷新、embedding 重算与 Graph View Projection 重建不改变 Authority revision。revision 用于精确状态识别与 stale-write 检测，不等同于面向人的长期历史版本。

有语义意义的 Authority 变化必须长期可追溯，至少能够说明原状态、修改原因、发生时间、依据与批准来源；由已批准操作必然引出的纯机械配套维护只需保留必要审计。正常更新、补充、纠错或适用边界变化在仍属于同一个可独立理解知识单元时保持原 identity 并产生新 revision；split、真正的 merge 或由新的长期知识单元替代旧单元属于 identity 级语义变化，必须经过既有用户批准治理。退役或被替代对象的旧 identity 默认永久保留且不得复用，除非用户明确要求物理删除并且删除语义要求不保留 tombstone。

关系记录的 identity 表示一个具体语义关系；改变 `source`、`type` 或 `target` 通常结束旧 relation 并创建新的 relation identity，而 provenance 补充或治理状态变化可以在同一 identity 上产生新 revision。材料记录 identity 表示材料进入 Knowledge 工作流及其 Knowledge 自有处理状态，不等于 URL、DOI、文件哈希或其他 Source identity。外部对象的 revision 始终由原 owner 管理，Knowledge 只保存必要的外部引用。Obsidian 人类导航继续使用 wikilink，但机器语义必须解析回稳定 identity，文件移动、重命名或 Projection 重建不得改变对象身份。
