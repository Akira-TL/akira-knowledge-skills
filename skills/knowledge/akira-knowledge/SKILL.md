---
name: akira-knowledge
description: 管理显式、持久、可检查、可更新和可复用的长期知识；0.1.x 基础 Knowledge Loop 与 0.2.x Retrieval + Views 均已闭合并通过发布就绪门禁。
disable-model-invocation: true
---

# Akira Knowledge

`akira-knowledge` 是 Akira Knowledge 0.x 系列的主要用户入口。它只负责识别知识工作意图、检查前置条件、选择 owning 工作流和停止边界；共同 Authority、identity、revision、修改治理与持久化规则以仓库 `CONTEXT.md` 和 accepted ADR 为准，不在各工作流中复制第二套规则。用户只需要表达知识任务，不需要记忆或直接指定领域 Skill 名称。

## 1. 意图路由

根据用户当前真实意图选择唯一 owning Skill，而不是通过固定关键词机械匹配：

- 明确要求长期保存、记下或加入知识库 → `knowledge-capture`；
- 要把材料整理、提炼、综合成长期知识、为既有知识形成语义修改提案，或提出 / 检查 / 批准 / 拒绝正式机器关系候选 → `knowledge-curate`；
- 要查找、筛选、全文搜索、按 stable identity 找回已有知识，或浏览当前知识 / 材料 / Relation Graph Projection → `knowledge-retrieve`；
- 要同步用户在 Obsidian 中的直接 edit / move / rename、执行已经批准的既有知识更新，或显式撤回已接受 Relation Record → `knowledge-maintain`。

一个请求跨越多个阶段时，Router 在 owning Skill 完成其有边界动作后重新判断下一意图。例如“把这段保存并整理成知识”先 Capture 得到材料记录，再进入 Curate；不能让 Capture 直接越权创建长期知识正文。

四个领域 Skill 共享 `akira-knowledge` 中的确定性工具和同一 SQLite / Markdown Authority 合同；领域 Skill 不各自建立数据库、sidecar、revision 规则或第二份正文真相。

## 2. Existing Vault bootstrap

首次接入一个新或已有 Obsidian Vault 时，必须先执行只读盘点：

```bash
uv run python <skill-root>/scripts/knowledge.py inspect --vault <vault>
```

`inspect` 只报告 Markdown 与 Akira Knowledge 系统状态，不创建 `.akira-knowledge/`、不移动文件、不写 Properties，也不把普通 Markdown 自动分类成 Knowledge 对象。

盘点后向用户明确展示建议的 Knowledge 管理范围、准备注册为长期知识资产的现有 Markdown，以及新对象默认写入根。只有用户明确批准这一语义范围后，才能执行 registration：

```bash
uv run python <skill-root>/scripts/knowledge.py register \
  --vault <vault> \
  --scope <approved-scope> \
  --note <approved-note.md> \
  --default-write-root <approved-root>
```

`--scope` 与 `--note` 可以重复。registration 必须使用用户批准的精确集合，不得把扫描到的其他 Markdown 顺带注册。

## 3. Registration contract

registration 原地完成：保留路径、正文、未知 Properties、tags、wikilinks、comments 与用户组织方式，只加入 Akira Knowledge 专用的稳定 identity / object kind，并建立 Vault 级配置和 SQLite registry / revision 基础。

Akira Knowledge 专用 Properties 当前为：

- `akira_knowledge_id`
- `akira_knowledge_kind`

它们属于 Knowledge-owned metadata。未注册 Markdown 若已经存在这些保留字段，必须 fail closed 并让用户显式处理冲突，不得静默接管其既有语义。

已有已注册对象再次执行 registration 时保持同一 identity；若检测到其人类 Authority 已经发生未同步修改，当前 bootstrap 命令停止，等待 revision-safe 更新工作流处理，不把 registration 当成覆盖入口。

## 4. 路由到 Capture

用户明确表达长期保存意图时，路由到 sibling `knowledge-capture` Skill，由它负责创建材料记录。Router 不自行复制 Capture 的进入条件、Source/provenance 或材料状态规则；普通任务上下文没有明确持久化意图时不得进入 Capture。

## 5. 路由到 Curate

用户要把一个或多个材料记录整理成长期知识、形成对既有知识资产的普通补充 / 纠错提案，或提出正式机器关系时，路由到 sibling `knowledge-curate` Skill。`0.3.x` 已实现 Relation Candidate 的提出、重新检查、批准与拒绝：Candidate 不是 Relation Authority，也不参与 traversal；只有用户明确批准后才创建或补充 Relation Record。相同 active triple 复用 relation identity，新 provenance 推进 relation revision，重复 provenance 不制造无意义 revision。模型推断、普通 wikilink、tag 或相似度不得自动升级关系；Router 不自行生成或直接写 Relation Record。

## 6. 路由到 Retrieval

用户要按 stable identity 找回对象、按 Authority 属性筛选、检索当前 Markdown 正文、希望“为当前任务取得相关知识”，或要在 Obsidian 中浏览当前知识 / 材料 / Relation Graph Projection 时，路由到 sibling `knowledge-retrieve` Skill。`0.2.x` 的基础检索默认只进入当前知识资产范围；用户明确需要材料记录时由 Retrieval 使用显式 scope 扩大本次请求范围。对于当前任务，Router / 当前 Agent 只负责把自然语言任务解释成显式、可检查的 retrieval plan，再交给 `knowledge-retrieve` 执行；计划可以组合 Exact / Filter / Full-text，并可沿 active Relation Record 做显式方向扩展。任务描述和 retrieval package 不成为新的 Knowledge 对象、Context 或 Memory。Obsidian Bases 与 Relation Graph 都只是可重建浏览 Projection，不拥有对象状态、关系状态或正文 Authority；revoked relation 不进入默认 traversal 或 active Graph Projection。Router 不通过修改对象状态来表达 scope，也不把普通 wikilink、tag 或模型相似度升级为 typed relation。Retrieval 对 Authority 保持只读；全文索引与动态视图等可重建 Projection 可以机械刷新，但不能因为命中结果或展示方式自动添加标签、链接、关系、权重或改写正文。

## 7. 路由到 Maintenance

用户要更新既有长期知识、已注册对象在 Obsidian 中发生 move / rename / direct edit 后准备继续写入，或明确撤回一个已接受 Relation Record 时，路由到 sibling `knowledge-maintain` Skill。普通正文更新仍先由 `knowledge-curate` 形成 proposal；Maintenance 负责同步 current revision、执行 stale-write 门禁并应用已批准 update。`0.3.x` 的 relation revoke 同样要求调用方携带实际读取的 expected revision；撤回保留 relation identity / triple / provenance / history，只把状态变为 revoked 并推进 revision，默认 traversal 随即排除。

## 8. Obsidian 执行边界

Akira Knowledge 决定知识语义与工作流，上游 Obsidian Skill 负责 Obsidian Flavored Markdown、Bases 和官方 CLI 等通用能力；本仓不创建 `knowledge-obsidian`。

真正依赖 Vault 语义的写操作，例如需要 Obsidian 自身处理链接或 Vault 状态的操作，优先复用 `kepano/obsidian-skills` 的 `obsidian-cli` 能力并使用执行时官方 CLI。官方 CLI 不可用时，只有该具体操作已经证明存在语义等价且满足 round-trip safety 的 filesystem fallback 才能继续，否则 fail closed。

当前已实现的 registration、Capture、新建知识资产、正文 body replacement，以及 `0.2.x` 的 `.base` Projection 生成，都是普通本地文件层操作，并分别通过 round-trip / Authority 黑盒测试验证，不依赖 Obsidian 特有的 link-aware move/rename 语义；因此这些路径可以直接使用共享的原子文件写入。当前版本不由 Knowledge 主动执行需要 Obsidian 语义的 rename / move；用户在 Obsidian 中发生的 move / rename 由 Maintenance 重新解析和同步。

## 9. 当前实现边界

`0.1.x` 基础 Knowledge Loop 与 `0.2.x` Retrieval + Views 均已实现，并分别通过 `docs/validation/0.1-release-gate.md` 与 `docs/validation/0.2-release-gate.md` 所记录的发布就绪黑盒门禁。`0.3.x` 正在实现 Knowledge Network；Relation Candidate 治理、stale protection、明确 approval、Relation Record 创建 / triple 去重 / provenance 增补、revision-safe 显式撤回、可重建 Obsidian Relation Graph Projection，以及从 Candidate → approval / rejection → traversal → Graph → revoke 的完整用户闭环已经闭合；最终独立黑盒与 0.2 → 0.3 升级兼容门禁仍由 #38 完成。系统性长期 Review、主动发现 stale / conflict relation 等能力继续按路线图延期到 `0.4.x`；不得把这些未完成能力描述为已经实现。通过发布就绪门禁仍不等于已经完成 GitHub tag / release 或远端安装发布。
