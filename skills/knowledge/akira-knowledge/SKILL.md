---
name: akira-knowledge
description: 管理显式、持久、可检查、可更新和可复用的长期知识；0.1.x 基础 Knowledge Loop 与 0.2.x Retrieval + Views 均已闭合并通过发布就绪门禁。
---

# Akira Knowledge

`akira-knowledge` 是 Akira Knowledge 0.x 系列的主要用户入口。它只负责识别知识工作意图、检查前置条件、选择 owning 工作流和停止边界；共同 Authority、identity、revision、修改治理与持久化规则以仓库 `CONTEXT.md` 和 accepted ADR 为准，不在各工作流中复制第二套规则。用户只需要表达知识任务，不需要记忆或直接指定领域 Skill 名称。

## 1. 意图路由

根据用户当前真实意图选择唯一 owning Skill，而不是通过固定关键词机械匹配：

- 明确要求长期保存、记下或加入知识库 → `knowledge-capture`；
- 要把材料整理、提炼、综合成长期知识、为既有知识形成语义修改提案，或提出 / 检查 / 批准 / 拒绝正式机器关系候选 → `knowledge-curate`；
- 要查找、筛选、全文搜索、按 stable identity 找回已有知识，或浏览当前 / 退役 / 已替代知识、材料 / Relation Graph Projection → `knowledge-retrieve`；
- 要同步用户在 Obsidian 中的直接 edit / move / rename、执行已经批准的既有知识更新、明确退役 / supersede 当前 Knowledge Asset、检查既有 Source、提出 / 检查 / 拒绝 semantic conflict candidate、执行 Relation maintenance Review、检查 Knowledge Network 健康、维护人类 wikilink / user Property，或组织多个既有治理项进行明确子集批准与 batch execution → `knowledge-maintain`。

一个请求跨越多个阶段时，Router 在 owning Skill 完成其有边界动作后重新判断下一意图。例如“把这段保存并整理成知识”先 Capture 得到材料记录，再进入 Curate；不能让 Capture 直接越权创建长期知识正文。

四个领域 Skill 共享 `akira-knowledge` 中的确定性工具和同一 SQLite / Markdown Authority 合同；领域 Skill 不各自建立数据库、sidecar、revision 规则或第二份正文真相。

## 2. 单 Vault 初始化与 Existing Vault bootstrap

Akira Knowledge 的默认产品形态是一个总 Obsidian Vault / Knowledge workspace：主题、项目与知识类型都位于同一 Vault 中，共享根级 `.akira-knowledge/knowledge.sqlite`，不按分类拆数据库。新建专用 Knowledge workspace 时使用 Primary Router 的初始化入口：

```bash
uv run python <skill-root>/scripts/knowledge.py init --vault <vault>
```

`init` 只负责 workspace bootstrap，不创建第二个专业 Skill。它保证 Vault 根是独立 Git repository 顶层，创建缺失的 `收件箱/`、`项目/`、`知识/`、`记录/`、`成果/`、`归档/`、`系统/` 与 `.assets/` 默认入口、根 `KNOWLEDGE.md`、`.akira-knowledge/` 配置与 SQLite store，并在 `AGENTS.md` 中维护 Akira Knowledge 自有指令块，明确要求 Agent 进入该工作区后先读取根 `KNOWLEDGE.md`。已有 `KNOWLEDGE.md` 不覆盖；已有 `AGENTS.md` 与 `.gitignore` 只更新 Akira Knowledge ownership marker 内的内容，用户其他规则必须原样保留。

根 `KNOWLEDGE.md` 是人类与 Agent 共用的顶层导航 Authority，只维护高层 Knowledge Map、主题 / 项目入口与工程工作区约定，不复制每个 Knowledge Asset、SQLite registry 或 Relation Authority，也不注册成普通 Knowledge Asset。Agent 先读它决定去哪个主题 / 项目区域，再通过 Retrieval Contract 精确找回具体知识。

Vault 可以包含代码、框架、原型、展示、报告和可复用 artifact；这些持久化 source 正常进入 Git。`node_modules/`、`.venv/`、常见 cache / build 目录、`.git/`、`.obsidian/`、`.akira-knowledge/`、`AK Views/` 与 `AK Graph/` 等工程噪声或可重建区域不参与 Knowledge 扫描，也不得显式 registration。默认 `.gitignore` 会忽略 Projection、依赖、cache、build 与 SQLite transient 文件，但不会默认忽略 `knowledge.sqlite` 结构化 Authority。

首次接入一个已有 Obsidian Vault 时，仍先执行只读盘点：

```bash
uv run python <skill-root>/scripts/knowledge.py inspect --vault <vault>
```

`inspect` 只报告可作为知识候选的 Markdown 与 Akira Knowledge 系统状态，并在遍历阶段剪掉依赖、虚拟环境、cache、build、Projection 与其他已定义工程噪声；不创建 `.akira-knowledge/`、不移动文件、不写 Properties，也不把普通 Markdown 自动分类成 Knowledge 对象。用户确认要把该 Vault 作为总 Knowledge workspace 后，再执行 `init` 建立根路由和工作区契约。

盘点后向用户明确展示建议的 Knowledge 管理范围、准备注册为长期知识资产的现有 Markdown，以及新对象默认写入根。只有用户明确批准这一语义范围后，才能执行 registration：

```bash
uv run python <skill-root>/scripts/knowledge.py register \
  --vault <vault> \
  --scope <approved-scope> \
  --note <approved-note.md> \
  --default-write-root <approved-root>
```

`--scope` 与 `--note` 可以重复。registration 必须使用用户批准的精确集合，不得把扫描到的其他 Markdown 顺带注册；根 `KNOWLEDGE.md`、`AGENTS.md`、依赖树、虚拟环境、cache / build 目录和 Projection 不属于可注册 Knowledge Asset。

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

用户要按 stable identity 找回对象、按 Authority 属性筛选、检索当前 Markdown 正文、希望“为当前任务取得相关知识”，或要在 Obsidian 中浏览当前 / 非当前知识、材料 / Relation Graph Projection 时，路由到 sibling `knowledge-retrieve` Skill。基础检索默认只进入当前知识资产范围；用户明确需要材料记录、已退役或已替代 Knowledge Asset 时，由 Retrieval 分别使用 `material` / `retired` / `superseded` 显式 scope 扩大本次请求范围。对于当前任务，Router / 当前 Agent 只负责把自然语言任务解释成显式、可检查的 retrieval plan，再交给 `knowledge-retrieve` 执行；计划可以组合 Exact / Filter / Full-text，并可沿 active Relation Record 做显式方向扩展。任务描述和 retrieval package 不成为新的 Knowledge 对象、Context 或 Memory。Obsidian Bases 与 Relation Graph 都只是可重建浏览 Projection，不拥有对象状态、关系状态或正文 Authority；revoked relation 不进入默认 traversal 或 active Graph Projection。Router 不通过修改对象状态来表达 scope，也不把普通 wikilink、tag 或模型相似度升级为 typed relation。Retrieval 对 Authority 保持只读；全文索引与动态视图等可重建 Projection 可以机械刷新，但不能因为命中结果或展示方式自动添加标签、链接、关系、权重或改写正文。

## 7. 路由到 Maintenance

用户要更新既有长期知识、已注册对象在 Obsidian 中发生 move / rename / direct edit 后准备继续写入、明确退役 / supersede 当前 Knowledge Asset、检查既有 Source、治理 semantic conflict / Relation maintenance candidate、检查 Knowledge Network orphan / unresolved / dead-end、修复人类 Authority 中的 wikilink / user Property、组织多个既有治理项进行明确子集批准与 batch execution，或明确撤回一个已接受 Relation Record 时，路由到 sibling `knowledge-maintain` Skill。普通正文更新仍先由 `knowledge-curate` 形成 proposal；Maintenance 负责同步 current revision、执行 stale-write 门禁并应用已批准 update。Knowledge Asset retire / supersede 都先形成绑定实际 revision 的 lifecycle proposal；Source Review、semantic conflict 与 Relation maintenance 则只形成绑定实际 identities / revisions / fingerprints / evidence 的待治理 Candidate，不直接改 Authority。Network health scan 保持只读；wikilink / user Property 修改先形成独立 revision-bound Authority edit proposal，只有明确批准后才写入。Batch 只引用这些既有 proposal / candidate 并独立保存各 item basis/result，不接受任意正文或 relation triple，也不建立新的 mutation 旁路。relation revoke 继续使用 expected revision 保护；新的 relation 语义继续走 Relation Candidate → approval。

## 8. Obsidian 执行边界

Akira Knowledge 决定知识语义与工作流，上游 Obsidian Skill 负责 Obsidian Flavored Markdown、Bases 和官方 CLI 等通用能力；本仓不创建 `knowledge-obsidian`。

真正依赖 Vault 语义的写操作，例如需要 Obsidian 自身处理链接或 Vault 状态的操作，优先复用 `kepano/obsidian-skills` 的 `obsidian-cli` 能力并使用执行时官方 CLI。官方 CLI 不可用时，只有该具体操作已经证明存在语义等价且满足 round-trip safety 的 filesystem fallback 才能继续，否则 fail closed。

当前已实现的 registration、Capture、新建知识资产、正文 body replacement，以及 `0.2.x` 的 `.base` Projection 生成，都是普通本地文件层操作，并分别通过 round-trip / Authority 黑盒测试验证，不依赖 Obsidian 特有的 link-aware move/rename 语义；因此这些路径可以直接使用共享的原子文件写入。当前版本不由 Knowledge 主动执行需要 Obsidian 语义的 rename / move；用户在 Obsidian 中发生的 move / rename 由 Maintenance 重新解析和同步。

## 9. 当前实现边界

`0.1.x` 基础 Knowledge Loop、`0.2.x` Retrieval + Views、`0.3.x` Knowledge Network 与 `0.4.x` Long-term Maintenance 均已完成对应发布就绪门禁。`0.4.x` 已通过最终独立 black-box 与真实 0.3 → 0.4 原地升级兼容门禁，包含 Knowledge Asset 明确退役 / supersede、真实 `retired` / `superseded` Retrieval Scope、对应 Bases 视图、可验证 Source Review → stale maintenance candidate、semantic conflict / Relation maintenance Review、只读 Knowledge Network health diagnostics、revision-safe wikilink / user Property Authority edit，以及只编排既有治理记录的 Batch Review / revision-safe maintenance。通过发布就绪门禁仍不等于已经完成 GitHub tag / release 或远端安装发布。
