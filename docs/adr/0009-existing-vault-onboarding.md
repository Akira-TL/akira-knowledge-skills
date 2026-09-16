---
status: accepted
---

# 已有 Obsidian Vault 原地接入而非全量迁移

Akira Knowledge 0.x 系列默认原地接入用户已有 Obsidian Vault，不要求复制到新的专用 Vault，也不把“接管资料库”等同于全量 import 或格式迁移。bootstrap 首先进行只读盘点；只有在用户明确 Knowledge 管理范围后，才对范围内已经确认属于长期 Knowledge 的 Markdown 做原地 registration，并且只补充 Knowledge 必需、ownership 已明确的最小机器 metadata。已有路径、正文、Properties、wikilink、标签与目录组织默认保持不变，一个 Vault 可以长期同时包含 Knowledge-managed 内容与普通 Obsidian 内容。

接入过程中，普通 Markdown 不因存在于 Vault 中就自动成为材料记录或知识资产；已有 Properties、tags 与 links 也不因字段名相似就自动升级成 Knowledge 工作流状态、对象类别或 typed relation。用户对管理范围的明确批准可以覆盖该范围内确定性的 stable identity / object kind 注入，无需逐篇确认，但批量写入仍必须满足 round-trip safety，且不得借 registration 顺便整理正文、重命名、搬迁、规范标签或重构目录。

只有当内容当前不属于目标 Vault，而用户明确要求纳入目标 Vault 时，才属于 import。0.x 后续 migration 只迁移 Akira Knowledge 自己拥有的 schema、字段、结构化 machine store 或可重建 Projection；版本升级不得借 migration 批量修改用户正文、标题、目录、普通导航链接或其他人类语义。新增全文索引、embedding、Bases、graph cache、relation type 等能力应优先通过增量结构化扩展或 Projection 重建进入后续版本，而不是反复改写人类 Markdown。
