---
name: knowledge-maintain
description: 执行 revision-safe 的显式知识更新、确定性状态同步、Knowledge Network 健康诊断、人类 Authority 链接/属性维护、Relation Record 显式撤回，以及 0.4.x lifecycle / Review 治理；在写入前阻止陈旧 revision 覆盖较新的 Authority。
---

# Knowledge Maintain

`knowledge-maintain` 负责显式用户触发的 revision-safe 更新和确定性状态同步；也负责把已经判断“无需继续沉淀”的 `待处理` 材料记录显式结案为 `已处理`。`0.3.x` 由本 Skill 执行已接受 Relation Record 的显式撤回，`0.4.x` 已增加 Knowledge Asset 的退役 / supersede lifecycle、可验证 Source Review → stale candidate、semantic conflict candidate、Relation maintenance Review、只读 Knowledge Network 健康诊断、受治理的人类 wikilink / user Property 修改，以及只编排既有治理记录的 Batch Review / maintenance。

## 1. Human-readable 正文维护边界

正文更新继续遵守 `<akira-knowledge-skill-root>/references/human-readable-writing.md`。Maintenance 不负责重新发明写作内容，但在执行已批准 update 时必须确认 proposal 已通过 Curate 的 Human-readable Writing Review。

不得以“统一格式”“润色”“让它更像知识库”为理由顺手重写未批准段落。对批准范围内实际触及的段落，应维持或改善标题可检索、重点前置、一个段落一个意思、句法直接、列表真实并列、verification 与不确定性表达明确等性质。

如果用户直接在 Obsidian 修改正文并导致当前 Authority 不符合写作合同，Maintenance 只能报告该问题或形成受治理的更新提案；不能绕过 Curate 直接大规模改写。

## 2. 同步当前对象状态

用户直接在 Obsidian 中移动、重命名或编辑已注册 Markdown 后，进入维护或写入准备时先同步对象：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-sync \
  --vault <vault> \
  --identity <stable-identity>
```

同步按 stable identity 在当前已批准 Knowledge 管理范围中重新解析 Markdown。若 current locator 改变，则登记 `external_move` revision；若人类内容 Authority fingerprint 改变，则登记 `external_edit` revision；两者同时发生时登记 `external_move_and_edit`。stable identity 始终不因这些变化改变。

Authority fingerprint 只用于已注册 Markdown 的外部内容变更检测，不是对象 identity，也不构成“对 Vault 所有文件做内容哈希”的要求。Knowledge-owned metadata 不作为人类正文 fingerprint 的语义内容。

材料记录的状态由结构化 Authority 拥有；如果用户手工修改了 Markdown 中的 `akira_knowledge_status` 镜像而与结构化状态不一致，维护流程必须把它视为 drift 并 fail closed，而不是把该镜像静默接管为 Authority。

## 3. 既有知识更新提案

既有知识的正文语义更新仍由 `knowledge-curate` 形成 proposal。形成候选正文前先执行 `maintain-sync`，记录返回的 current revision，再读取当前 Authority；`knowledge-curate` 保存 update proposal 时必须携带这个实际读取的 `base_revision`。proposal 保存阶段会再次同步目标，如果期间 revision 已变化则立即停止，防止把基于旧正文生成的 proposal 错绑到新状态。依据材料也在 proposal 保存前同步并记录 basis revision。

用户未明确批准时，不调用任何应用命令，Knowledge Authority 保持不变。

用户明确批准 update proposal 后，由本 Skill 执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-apply-update \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

执行前再次同步目标与材料。若 proposal 的 `base_revision` 之后出现 `external_edit`、`external_move_and_edit` 或其他不能机械证明与正文更新互不相交的 Authority 变化，则 fail closed，保留当前较新的 Authority，并要求从当前 revision 重新形成 proposal。

纯 `external_move` 只改变 locator，可以机械证明与已批准的正文替换互不相交，因此允许在新的 canonical locator 上继续执行。当前版本不做猜测式语义三方合并。

## 4. 应用更新

通过 revision 门禁后，只替换知识资产的人类正文 body，保留现有 YAML frontmatter、用户 Properties 与 Akira Knowledge identity / kind。成功写入后：

- 同一 stable identity 保持不变；
- current locator 使用同步后的实际路径；
- Authority revision 单调推进；
- revision history 记录 `updated_from_proposal`；
- proposal 记录为 applied，并关联原 target identity；
- proposal 的材料 provenance 写入结构化 Authority；
- 仍为 `待处理` 的依据材料可以确定性进入 `已处理`，材料本身不删除。

Projection / 全文索引重建不得推进 Authority revision；这一职责继续由 `knowledge-retrieve` 的可重建 Projection 机制承担。

### 材料记录无需沉淀时的显式结案

材料被阅读、核验后，用户可能明确判断它只需要保留作来源或参考，不值得创建 / 更新任何 Knowledge Asset。此时不得伪造一个空 proposal，也不得让材料永久停留在 `待处理`；先同步并读取材料当前 revision，再执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-resolve-material \
  --vault <vault> \
  --identity <material-id> \
  --expected-revision <actually-read-revision> \
  --reason <why-no-durable-knowledge-is-needed> \
  --confirmed-resolution
```

该操作只允许作用于仍为 `待处理` 的 Material Record，并要求用户明确确认与非空 reason。执行前重新同步对象；revision 已变化时 fail closed。成功后只把结构化材料状态与 Markdown 中的 Knowledge-owned 状态镜像改为 `已处理`，记录 `material_resolved` revision 和 reason；材料正文、Source、provenance 与 stable identity 保留，不创建 Knowledge Asset，也不删除材料。写入后的 Authority fingerprint 必须对应实际修改后的 Markdown，因此随后无其他改动的 `maintain-sync` 不得制造额外 `external_edit` revision。

## 5. Knowledge Asset 明确退役

用户明确决定某个当前 Knowledge Asset 不再进入默认当前知识范围时，先基于实际读取的 current revision 形成退役提案：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-retire \
  --vault <vault> \
  --identity <knowledge-asset-id> \
  --base-revision <actually-read-revision> \
  --reason <retire-reason>
```

提案只保存待治理的 lifecycle 变化，不立即修改 Authority。用户明确批准后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-apply-retire \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

批准执行前重新同步目标；若目标 revision 已不同，提案 fail closed 并保持 pending。成功退役后：

- stable identity、canonical Markdown、history 与既有 provenance 保留；
- Knowledge Asset revision 单调推进；
- structured lifecycle Authority 进入 `retired`；
- Markdown 中的 `akira_knowledge_lifecycle: retired` 只是 Knowledge-owned 机器维护表示，不成为第二 Authority；
- 默认 `current` Retrieval Scope 排除该对象；
- 显式 `retired` scope 仍可通过 Exact / Filter / task retrieval 回读同一 identity；
- Material Record 的 `待处理 / 已处理` 状态不受影响。

退役不等于 supersede；退役不记录 replacement target。

## 6. Knowledge Asset 明确替代

用户明确决定一个当前 Knowledge Asset 已由另一个当前 Knowledge Asset 承担后续职责时，先同时绑定旧对象与 replacement 的实际 revision：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-supersede \
  --vault <vault> \
  --identity <old-knowledge-asset-id> \
  --base-revision <old-actually-read-revision> \
  --replacement-id <replacement-knowledge-asset-id> \
  --replacement-revision <replacement-actually-read-revision> \
  --reason <supersede-reason>
```

proposal 创建要求两端都是不同且当前有效的 Knowledge Asset。用户明确批准后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-apply-supersede \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

执行前重新同步旧对象与 replacement；任一 revision 或 lifecycle 已变化都 fail closed。成功 supersede 后：

- 旧 stable identity、canonical Markdown、history 与既有 provenance 保留；
- 只推进旧对象 revision，replacement identity / revision 保持独立；
- structured lifecycle Authority 记录旧对象为 `superseded`，并记录 replacement stable identity 与 reason；
- Markdown 中 `akira_knowledge_lifecycle: superseded` 只是机器维护镜像；
- 默认 `current` scope 排除旧对象；显式 `superseded` scope 仍可回读旧 identity；
- replacement 继续作为自己的 `current` Knowledge Asset；
- 已非 current 的对象不会被 retire / supersede 命令静默改写成另一 lifecycle。

## 7. Source Review 与陈旧候选

当用户要求系统性检查某个当前 Knowledge Asset 的既有 Source 时，先从公开入口取得其 provenance Source 集合，不直接查询 SQLite：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-review-plan \
  --vault <vault> \
  --identity <knowledge-asset-id>
```

该计划只返回当前 target identity / revision / fingerprint / canonical locator、当前 lifecycle，以及从既有 material provenance 链确定性得到的 Source locator；若该 Source 之前已有可验证的 `changed` / `unchanged` observation，还返回最近一次 `last_verified` source identity / revision / fingerprint / evidence，供下一轮比较直接作为可靠 basis。临时 `unknown` finding 不覆盖最近一次已验证 observation。计划不会创建 finding / candidate，也不会修改语义 Authority。

当前 Agent 再使用执行时真实可用且适合每个 Source 的访问能力逐项完成核验。确定性后端不自行联网，也不接受单纯的“changed=true”结论；调用方必须提供此次实际比较的 basis / observed Source identity、revision、fingerprint 与证据。

确认能够比较时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-review-source \
  --vault <vault> \
  --identity <knowledge-asset-id> \
  --source <source-locator> \
  --basis-source-id <basis-source-identity> \
  --basis-revision <basis-revision> \
  --basis-fingerprint <basis-fingerprint> \
  --observed-source-id <observed-source-identity> \
  --observed-revision <observed-revision> \
  --observed-fingerprint <observed-fingerprint> \
  --evidence <verified-evidence>
```

如果当前无法确认 Source revision / fingerprint，使用 `--unknown`，并省略 observed 三项。若已有 `last_verified` 或其他可靠历史 basis，可以同时保留完整 basis 三项；若恰恰因为没有稳定比较依据而无法确认，则 basis 三项也应全部省略，外部结果明确返回 `basis: null`，不得编造 revision / fingerprint。此时只记录 `unknown` Review finding，不生成 stale candidate。

后端要求该 Source locator 确实位于目标 Knowledge Asset 的 material provenance 链；observed Source identity 与 basis identity 不一致时 fail closed，不把重定向到另一 owner 的内容当作原 Source 的新 revision。

只有 identity 一致且 revision 或 fingerprint 确实变化时，才形成 `source_stale` maintenance candidate。Candidate 绑定创建时目标 Knowledge identity / revision / fingerprint、Source basis / observed 状态和 evidence，但它不是 Knowledge Asset、Relation Record，也不自动修改正文、lifecycle、relation 或 provenance Authority。

检查 Candidate：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-inspect-review-candidate \
  --vault <vault> \
  --candidate-id <candidate-id>
```

若目标 Authority 在 Candidate 创建后发生变化，pending Candidate 转为 `stale`，必须基于当前 Authority 重新 Review。用户明确拒绝 pending / stale Candidate 时：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-reject-review-candidate \
  --vault <vault> \
  --candidate-id <candidate-id> \
  --confirmed-rejection
```

Review Candidate 不提供直接“批准并改 Authority”的旁路。需要正文更新时继续进入 `knowledge-curate` 的 update proposal → approval；需要 retire / supersede 时继续使用本 Skill 的 lifecycle proposal。

## 8. Semantic Conflict Candidate

当前主模型在实际读取两个或多个当前治理对象后，如果判断它们可能无法同时成立，只能形成待治理 conflict candidate，不直接修改任何 Authority：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-conflict \
  --vault <vault> \
  --knowledge-id <optional-current-knowledge-id> \
  --source-finding-id <optional-source-review-finding-id> \
  --relation-id <optional-active-relation-id> \
  --conflict <semantic-conflict-statement> \
  --evidence <actual-review-evidence>
```

至少需要两个不同治理成员。当前支持的 member basis 为 current Knowledge Asset、Source Review finding 与 active Relation Record。Candidate 固定每个成员创建时实际读取的 identity / ref、revision、fingerprint 与 locator/basis；普通 wikilink、tag、全文共现或模型相似度本身不能自动升级成 conflict member，更不能因此创建、修改或撤回 Relation Record。

重新检查：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-inspect-conflict \
  --vault <vault> \
  --candidate-id <candidate-id>
```

任一 Knowledge / Source finding basis / Relation revision 或 fingerprint 变化时，pending Candidate 转为 `stale`。用户明确拒绝：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-reject-conflict \
  --vault <vault> \
  --candidate-id <candidate-id> \
  --confirmed-rejection
```

拒绝只改变 Candidate governance 状态，不修改 Knowledge / lifecycle / Relation Authority。当前实现不引入 ontology、inverse / symmetry / transitive inference 或自动规则推理。

## 9. Relation maintenance Review

对 active Relation Record 形成 stale / conflict maintenance candidate 时：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-relation-maintenance \
  --vault <vault> \
  --relation-id <relation-id> \
  --kind <relation_stale|relation_conflict> \
  --source-finding-id <optional-source-review-finding-id> \
  --evidence <review-evidence>
```

Candidate 固定 Relation identity / revision / deterministic fingerprint，以及本地 source / target endpoint revision / fingerprint；如果 Review 依赖一个 Source finding，还同时固定该 finding 的 target basis。inspect 时 relation revision/provenance、endpoint Authority 或绑定 evidence basis 任一变化都会使 pending Candidate 转为 `stale`：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-inspect-relation-maintenance \
  --vault <vault> \
  --candidate-id <candidate-id>
```

Relation maintenance Candidate 没有 apply 命令，也不能原地改变既有 source / type / target triple。真正需要撤回时继续使用 `relation-revoke --expected-revision`；需要新的 relation 语义时继续使用 `relation-propose → relation-approve`。用户也可以通过 `maintain-reject-relation-maintenance --confirmed-rejection` 拒绝候选而不修改 Relation Authority。

## 10. Knowledge Network 健康诊断与链接 / 属性维护

需要检查当前 Knowledge-managed 网络时，使用只读入口：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-health-scan \
  --vault <vault>
```

诊断只观察当前 Knowledge Asset 的可解析普通 wikilink 与 active Relation Record，返回：

- `orphan`：没有可解析 incoming / outgoing navigation 或 active relation 的当前 Knowledge Asset；
- `unresolved`：普通本地 Knowledge wikilink 无法解析到唯一 canonical target，并返回 source identity / locator 与原始 wikilink evidence；
- `dead_end`：能被其他当前对象到达，但自身没有可解析向外 navigation / active relation 的当前 Knowledge Asset。

诊断不创建 Relation Record、不加 tag、不改 lifecycle，也不持久化第二份网络 Authority；重复扫描不得推进 Knowledge / Relation revision。若一个本地引用存在多个 canonical candidate，必须 fail closed，而不是把它记成普通 unresolved。

需要修复**人类 Authority**中的 wikilink 或 user Property 时，先形成 revision-bound proposal。wikilink 示例：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-authority-edit \
  --vault <vault> \
  --identity <knowledge-asset-id> \
  --base-revision <actually-read-revision> \
  --replace-wikilink <old-target> <new-target> \
  --reason <reason>
```

user Property 示例：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-authority-edit \
  --vault <vault> \
  --identity <knowledge-asset-id> \
  --base-revision <actually-read-revision> \
  --set-property <key> <value> \
  --reason <reason>
```

proposal 阶段只保存完整拟议 Authority 文本，不写 Markdown。它必须保留未知 frontmatter、无关正文、comments 与用户格式；Akira Knowledge-owned Property 不允许通过该人类 Authority edit 路径修改。

用户明确批准后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-apply-authority-edit \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

执行前重新同步目标；只要 current revision 不再等于 proposal base revision，就按 stale fail closed，不覆盖用户期间产生的较新 edit / move。成功后保持 stable identity，推进 Knowledge revision，并在 revision ledger 记录 `authority_edit_applied`。该路径只修改已批准的人类 Authority，不自动创建 typed relation。

## 11. Relation Record 显式撤回

用户明确要求撤回一个当前正式关系时，调用方必须先读取该 Relation Record 的当前 revision，并在确认后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py relation-revoke \
  --vault <vault> \
  --relation-id <relation-id> \
  --expected-revision <actually-read-revision> \
  --confirmed-revoke
```

撤回只允许在调用方实际读取的 expected revision 仍等于当前 relation revision 时执行；如果其间 relation 因 provenance 增补或其他 Authority 变化推进了 revision，则 fail closed，要求重新读取并再次确认。

成功撤回：

- 保留 relation stable identity；
- 保留 source / type / target；
- 保留全部 provenance 与 revision history；
- relation status 进入 `revoked`；
- relation revision 单调推进；
- 默认 typed relation traversal 不再消费该关系；
- 不物理删除 Relation Record。

对已经 revoked 的关系，如果调用方提供的 expected revision 正好等于当前 revision，则作为幂等操作返回，不再次推进 revision；若使用旧 revision 重复操作，仍按 stale-write 规则 fail closed。

撤回是实际 Relation Authority mutation；Relation stale / conflict Review 只产生待治理 Candidate。两者边界保持分离，Review 不得绕过 expected-revision revoke 或 Relation Candidate / approval 合同。

## 12. Batch Review 与批量 revision-safe maintenance

一次系统性 Review 需要组织多个已经存在的 governed proposal / candidate 时，可以创建 maintenance batch。Batch **不接受任意正文、任意 target 或任意 relation triple**，只能引用既有治理记录：

- Knowledge update proposal；
- retire / supersede lifecycle proposal；
- human Authority edit proposal；
- Relation Candidate；
- Relation maintenance candidate 对应的 expected-revision revoke。

创建：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-batch-create \
  --vault <vault> \
  --update-proposal <proposal-id> \
  --retire-proposal <proposal-id> \
  --supersede-proposal <proposal-id> \
  --authority-edit-proposal <proposal-id> \
  --relation-candidate <candidate-id> \
  --relation-revoke-candidate <relation-maintenance-candidate-id>
```

每个 item 独立保存自己的 governance ref、target / relation identity、创建时实际读取的 revision / fingerprint basis、evidence 与 proposed semantic change。Batch 本身不是 Knowledge Object，也不拥有正文、lifecycle、relation 或 provenance Authority。

用户必须明确批准要执行的 item 子集：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-batch-approve \
  --vault <vault> \
  --batch-id <batch-id> \
  --item-id <approved-item-id> \
  --confirmed-approval
```

未被选择的 pending item 明确进入 `rejected`，批准动作本身不执行任何 Authority mutation。

执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-batch-execute \
  --vault <vault> \
  --batch-id <batch-id>
```

执行前逐项重新读取 basis。某一 item 的 revision / fingerprint 已变化时，该项记为 `stale`，不得覆盖新 Authority；其他机械独立且仍 fresh 的 approved item 可以继续执行。执行结果逐项返回 `succeeded / stale / failed / rejected`，Batch 只有全部可执行项成功时才是 `completed`；存在 stale / failed 时明确为 `partial`。

真正写入仍由原有治理 workflow 完成：Knowledge update 继续 `apply_update_proposal`，retire / supersede 继续 lifecycle apply，Authority edit 继续 explicit approval apply，Relation Candidate 继续 approval，撤回继续 expected-revision revoke。Batch 没有新的通用写入口。

已经 `succeeded` 的 item 是终态；重复执行同一 Batch 不再次调用其 mutation，不制造无意义 revision。Projection rebuild 只反映已经成功的 Authority mutation，本身仍不得推进额外 revision。

## 13. 停止边界

以下情况必须停止而不是覆盖或猜测：

- stable identity 在当前管理范围内找不到唯一 Markdown；
- object kind 与结构化 registry 不一致；
- proposal 不是 pending update proposal；
- 没有明确用户批准；
- proposal target 或依据材料在 basis revision 后发生相关 Authority 编辑；
- Knowledge-owned 状态镜像与结构化 Authority 漂移；
- Source 不属于目标 Knowledge provenance、Source identity 无法保持一致，或 Source 当前状态无法被可靠比较；
- Review Candidate 的目标 basis 已变化；
- 本地 Knowledge wikilink 无法唯一解析；
- human Authority edit proposal 的 base revision 已过期；
- 试图通过 human Authority edit 修改 Knowledge-owned Property；
- Batch item 的治理记录不是 pending/可执行状态，或 item basis 已变化；
- Batch 试图引用不存在或不属于既有治理类型的 mutation；
- 结构化 Authority store 不可读取。

`0.1.x` 不引入多 Agent 锁、claim、并发仲裁或自动语义 merge；这些也不属于 Akira Knowledge 当前产品职责。
