---
name: akira-knowledge
description: 管理显式、持久、可检查、可更新和可复用的长期知识；当前 0.1 实现从 Obsidian Vault bootstrap / registration 开始，并逐步路由 capture、curate、retrieve 与 maintain 工作流。
disable-model-invocation: true
---

# Akira Knowledge

`akira-knowledge` 是 Akira Knowledge 0.x 系列的主要用户入口。它只负责识别知识工作意图、检查前置条件、选择 owning 工作流和停止边界；共同 Authority、identity、revision、修改治理与持久化规则以仓库 `CONTEXT.md` 和 accepted ADR 为准，不在各工作流中复制第二套规则。用户只需要表达知识任务，不需要记忆或直接指定领域 Skill 名称。

## 1. 意图路由

根据用户当前真实意图选择唯一 owning Skill，而不是通过固定关键词机械匹配：

- 明确要求长期保存、记下或加入知识库 → `knowledge-capture`；
- 要把材料整理、提炼、综合成长期知识，或为既有知识形成语义修改提案 → `knowledge-curate`；
- 要查找、筛选、全文搜索或按 stable identity 找回已有知识 → `knowledge-retrieve`；
- 要同步用户在 Obsidian 中的直接 edit / move / rename，或执行已经批准的既有知识更新 → `knowledge-maintain`。

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

用户要把一个或多个材料记录整理成长期知识，或要形成对既有知识资产的普通补充 / 纠错提案时，路由到 sibling `knowledge-curate` Skill。Router 不自行生成或应用长期知识正文；proposal / approval 与材料处理状态维护由 `knowledge-curate` 拥有。

## 6. 路由到 Retrieval

用户要按 stable identity 找回对象、按 Authority 属性筛选或检索当前 Markdown 正文时，路由到 sibling `knowledge-retrieve` Skill。Retrieval 对 Authority 保持只读；全文索引等可重建 Projection 可以机械刷新，但不能因为命中结果自动添加标签、链接、关系、权重或改写正文。

## 7. 路由到 Maintenance

用户要更新既有长期知识，或已注册对象在 Obsidian 中发生 move / rename / direct edit 后准备继续写入时，路由到 sibling `knowledge-maintain` Skill。普通正文更新仍先由 `knowledge-curate` 形成 proposal；Maintenance 负责同步 current revision、执行 stale-write 门禁，并在明确批准后应用 update。

## 8. Obsidian 执行边界

Akira Knowledge 决定知识语义与工作流，上游 Obsidian Skill 负责 Obsidian Flavored Markdown、Bases 和官方 CLI 等通用能力；本仓不创建 `knowledge-obsidian`。

真正依赖 Vault 语义的写操作，例如需要 Obsidian 自身处理链接或 Vault 状态的操作，优先复用 `kepano/obsidian-skills` 的 `obsidian-cli` 能力并使用执行时官方 CLI。官方 CLI 不可用时，只有该具体操作已经证明存在语义等价且满足 round-trip safety 的 filesystem fallback 才能继续，否则 fail closed。

当前 `0.1.x` 已实现的 registration、Capture、新建知识资产与正文 body replacement 都是普通本地文件层操作，并分别通过 round-trip / Authority 黑盒测试验证，不依赖 Obsidian 特有的 link-aware move/rename 语义；因此这些路径可以直接使用共享的原子文件写入。当前版本不由 Knowledge 主动执行需要 Obsidian 语义的 rename / move；用户在 Obsidian 中发生的 move / rename 由 Maintenance 重新解析和同步。

## 9. 当前实现边界

当前 `0.1.x` 已实现 Vault bootstrap / registration、显式 Capture、Curate 的 proposal → approval、新建知识资产、Exact / Filter / Full-text 基础 Retrieval，以及既有知识的 revision-safe update。系统性长期 Review、主动陈旧/冲突候选与最终 0.1.x 发布门禁仍属于后续版本/门禁；不得把这些缺失能力伪装成已完成，也不得自行用临时 Markdown/SQLite 操作绕过 owning Skill。
