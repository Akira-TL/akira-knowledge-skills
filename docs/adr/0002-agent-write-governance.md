---
status: accepted
---

# Agent 写入治理与同步冲突处理

Akira Knowledge 将 Agent 写入权限按语义风险而不是按“人类层 / 机器层”二分。人类内容 Authority 的语义修改必须先向用户展示拟变更并取得明确批准；批准对象是一个明确的语义变更集，执行时可以自动完成由该批准必然引出的确定性配套维护，但不得扩张为新的语义决定。结构化 Authority 中，真实操作、明确用户动作或确定性流程产生的 provenance、lineage、材料状态等可以自动维护；模型推断出的标签、关系、冲突、适用性或 identity 判断在治理接受前只能保持为 candidate / Projection。所有人类可编辑表示的修改必须最小化并保持 round-trip safety，未知字段、无关正文、用户格式、链接与注释不得因序列化被顺带改写。Authority 与 Projection 冲突时按 ownership 解决，不使用 last-write-wins；Projection 从 Authority 重建。执行已批准变更前必须重新读取相关 Authority，若其后发生可能冲突的修改则 fail closed 并重新提案，只有可以机械证明互不相交的变化可以继续。