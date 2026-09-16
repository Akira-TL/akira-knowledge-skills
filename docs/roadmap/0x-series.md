# Akira Knowledge 0.x 系列路线图

本文定义 1.0 之前的 0.x 系列能力版图与 minor 版本切分原则。它建立在已接受的共同产品基线上，不重新定义领域对象、Authority / Projection、修改治理、Obsidian 边界、identity / revision、持久化职责或已有 Vault 接入规则。

## 版本规划原则

- 路线图规划到 `0.N.x` minor 系列；patch 版本由真实实现后的 bugfix、兼容修正和小幅完善决定，不预先分配功能。
- 每个 minor 都必须形成独立用户价值闭环：升级后用户应能完成此前不能完成的一类长期知识任务。
- 冻结的是能力域、依赖顺序、进入条件和共同不变量，不冻结未来永远只能使用当前这些 minor 编号；若真实需求出现新的稳定能力域，可以在不破坏共同基线的前提下插入新的 minor。
- Canvas、大型 ontology、第二套人类 UI、ContextD 集成、多 Agent 写入协议与通用 Skill package manager 不属于当前 0.x 主路线。

## 0.x 能力域

0.x 系列覆盖七个能力域：

1. **Vault 基础与接入**：已有 Vault bootstrap、Knowledge 管理范围、stable identity / revision、Markdown + frontmatter + SQLite、import、migration、rebuild 与 recovery。
2. **捕获与材料管理**：低摩擦 Capture、材料记录、待处理 / 已处理、Source 引用、待整理视图与去重候选。
3. **知识沉淀与整理**：材料转长期知识资产、多材料综合、既有知识修改、用户批准、split / merge / supersede、provenance / history 与普通导航链接维护。
4. **检索与任务知识上下文**：exact、filter、full-text、typed relation 基础 Retrieval Contract，任务相关知识集合、召回依据、canonical Authority 回读与 Bases 等动态视图；后续可以按证据增加 embedding、vector retrieval、rerank 或 graph ranking。
5. **知识网络与机器关系**：typed relation、relation candidate、relation provenance、Graph View 机器 Markdown Projection，以及人类 wikilink 与机器关系分层浏览。
6. **长期维护**：Review、陈旧信息候选、冲突候选、Source 更新检查、retired / superseded、orphan / unresolved / dead-end 检查、属性和链接维护、批量修订提案。
7. **稳定性与规模化**：大 Vault 行为、增量索引、Projection 重建、SQLite migration、恢复、诊断、损坏检测、round-trip safety 回归验证、长期历史规模控制与 1.0 前数据契约稳定。

## Minor 路线

### 0.1.x — 基础 Knowledge Loop

目标：让用户能够安全地把材料沉淀为正式长期知识，并在 Obsidian 中持续维护。

包含：Vault bootstrap、Capture、Curate、Knowledge Asset、stable identity / revision、Markdown + frontmatter + SQLite 基础、用户批准治理、最小 provenance，以及基础 exact / filter / full-text retrieval。

暂不要求复杂机器关系、系统性长期维护、向量检索或大型性能优化。

### 0.2.x — Retrieval + Views

目标：让已有知识真正参与新的任务，而不只是被保存。

增加：完整基础 Retrieval Contract、任务相关知识集合、matched evidence / retrieval reason、检索范围控制，以及材料、当前知识、retired 等 Bases / 动态视图。

该阶段仍不要求独立向量数据库。

### 0.3.x — Knowledge Network

目标：在可靠存储和检索之上，让系统利用经过治理的知识关系。

增加：typed relation 完整工作流、relation candidate、relation provenance、relation traversal、Graph View 机器 Markdown Projection，以及人类导航链接与机器关系的联合浏览。

### 0.4.x — Long-term Maintenance

目标：让 Knowledge 从“会存会找”进入可长期保持可用的状态。

增加：`knowledge-maintain` 的系统能力，包括 Review triggers、stale / conflict candidates、Source 更新检查、retire / supersede、orphan / unresolved / dead-end 检查、链接与属性维护、批量修订 proposal。

`knowledge-maintain` 的 Skill 职责从共同基线开始存在，但其系统性长期维护能力到本阶段才完整。

### 0.5.x — Semantic Retrieval Enhancement

目标：只有在 0.1–0.4 的真实使用或检索评测证明基础 Retrieval Contract 不足时，按证据提高复杂语义召回质量。

候选技术包括 embeddings、vector retrieval、hybrid retrieval、rerank 与 graph ranking，但路线图只承诺“语义检索增强”这一能力域，不预先承诺某个向量数据库、具体 backend 或某项技术一定实施。若基础检索已经满足需求，可以缩减或重新定义这一阶段。

### 0.6.x — Scale + Reliability

目标：从个人实验性使用进入更大 Vault 和更长期真实使用。

增加：large-vault performance、incremental indexing、Projection rebuild、recovery、migration、diagnostics、corruption detection、round-trip safety regression，以及长期历史规模控制。

### 0.7.x / 0.8.x — 按真实需求保留

不为填版本号预先发明功能。只有真实使用发现新的稳定能力域，并且它不能自然归入现有阶段时，才在这里或其他合适位置插入新的 minor。

### 0.9.x — 1.0 Stabilization

目标：准备进入稳定 1.0，不再引入新的大型能力域。

重点包括：0.x 数据兼容性收口、领域合同冻结候选、migration 验证、破坏性操作与恢复场景、完整 Skill 路由验收、文档与安装依赖验收，以及判断哪些 0.x 实验性能力正式进入 1.0。

## 依赖顺序

主依赖顺序保持：

`可靠形成知识 → 可靠找回知识 → 利用机器关系 → 系统维护长期知识 → 按证据增强语义检索 → 规模化与可靠性 → 1.0 稳定化`

图谱与 typed relation 机制虽然属于共同产品基线，但完整产品能力不排在基础检索之前；向量与其他语义增强也不得先于可解释、可降级的基础 Retrieval Contract。
