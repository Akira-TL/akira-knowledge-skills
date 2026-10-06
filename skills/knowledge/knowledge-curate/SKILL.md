---
name: knowledge-curate
description: 把材料整理成长期知识正文提案、为既有知识形成更新提案，并在 0.3.x 中形成受治理的关系候选（Relation Candidate）；候选内容只有在后续明确批准后才能成为 Authority。
---

# Knowledge Curate

`knowledge-curate` 负责整理、提炼与综合材料，并通过 proposal → explicit approval 的治理边界创建或修改长期知识；`0.3.x` 还由本 Skill 负责形成关系候选（Relation Candidate）并处理候选的检查 / 拒绝。它不负责低摩擦 Capture，也不绕过 revision-safe 更新规则，更不能把模型推断的关系直接写成 Relation Record Authority。

## 1. 形成提案

每次形成新建或正文更新 proposal 前，必须先读取共享写作合同：

```text
<akira-knowledge-skill-root>/references/human-readable-writing.md
```

读取用户指定或当前工作流选定的一个或多个材料记录，由当前主模型直接形成拟长期保存的正文。提案必须是一个可独立理解、值得长期维护和未来检索的高内聚知识单元；不得机械要求一条资产只包含一个 Claim 或 Concept，也不得把多个能够独立检索的问题拼成“大而全”的长文。

Knowledge Asset 是给人长期查阅的参考文档，不是对话记录、Agent 思考过程、一次性分析报告或材料摘要堆叠。正文必须至少做到：

- 标题具体、可搜索，并能代表正文边界；
- 一级标题后直接给定义、结论、用途、适用范围或核心问题，不写生成式铺垫；
- 一个普通段落表达一个完整意思，既不形成墙状长段，也不连续堆叠碎片化单句段；
- 小节标题描述读者实际能找到的内容，层级连续；
- 列表只表示真实并列或顺序，连续论述使用段落；
- 事实、方法建议、构想和待核验内容显式区分；
- 需要复用已有知识时优先 wikilink 到 owning Knowledge Asset，不复制整段制造多份 Authority；
- 删除“本文将”“下面首先”“值得注意的是”“从上述分析可以看出”“综上所述”等不增加语义的 AI 元话语。

完整句长、段落、列表、标题、aliases、不同知识类型默认骨架与反 AI 写作规则以共享 reference 为准。

在把候选正文写入 proposal store 之前，必须先执行 Human-readable Writing Review。主模型按共享 reference 完成语义自检。

新建 Knowledge Asset 时运行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py writing-check \
  --body-file <proposal-body-file> \
  --strict
```

更新既有 Knowledge Asset 时使用当前 Authority 作为 baseline：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py writing-check \
  --baseline-file <current-authority-file> \
  --body-file <proposal-body-file> \
  --strict
```

baseline 模式只阻止新增或加重的结构 / 风格问题。已有写作债务不会因为一次无关语义更新而强迫顺手重写；需要系统性润色时应单独形成明确的正文更新提案。

确定性 checker 只检查明确结构问题和高置信风格 findings，不负责判断事实真伪。新建 proposal 必须清零 finding；update proposal 不得产生新的 regression。后端会再次执行同一门禁，不能通过跳过命令绕过。

把通过 review 的候选正文写入 proposal store：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py curate-propose \
  --vault <vault> \
  --material-id <material-id> \
  --body-file <proposal-body-file>
```

为既有知识资产提出补充、纠错或适用边界修改时，必须先由 `knowledge-maintain` 执行 `maintain-sync` 得到当前 revision，再读取该 revision 对应的当前 Authority 并据此形成候选正文。保存 update proposal 时同时提供实际读取的基线：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py curate-propose \
  --vault <vault> \
  --material-id <material-id> \
  --target-id <knowledge-asset-id> \
  --base-revision <actually-read-revision> \
  --body-file <proposal-body-file>
```

保存 proposal 时工具会再次同步目标；若 revision 已不同，说明“读取 → 形成 proposal”期间 Authority 又发生变化，必须 fail closed 并重新读取，而不能把旧内容生成的 proposal 绑定到新 revision。proposal 是 candidate，不是人类内容 Authority；创建 proposal 不得改写目标知识 Markdown。

向用户展示拟批准的语义变更集：目标是新建还是更新、拟正文、依据材料、Human-readable Writing Review 结果，以及会发生的确定性 metadata / provenance / 状态维护。不得把 proposal 持久化本身描述成“知识已经更新”。

## 2. 用户批准或拒绝

用户明确批准“新建知识资产”提案后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py curate-approve \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

批准后才创建 Obsidian Markdown 知识资产、稳定 identity、初始 revision 与材料 provenance。由该批准必然引出的材料状态更新可以自动完成：材料记录保留原文件与 provenance，只把结构化 Authority 中的状态从 `待处理` 更新为 `已处理`，并推进对应 revision；Markdown 中同名的 Akira Knowledge 状态 Property 只是该结构化状态的机器维护 Projection，不成为第二份可独立编辑 Authority。

用户明确拒绝时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py curate-reject \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-rejection
```

拒绝不得创建或修改知识资产 Authority。

## 3. 既有知识更新边界

既有知识资产的普通补充、纠错或适用边界修改仍在本 Skill 生成 update proposal；形成 proposal 前共享后端会同步目标对象与依据材料，使 proposal 绑定当前 `base_revision`。用户明确批准后，实际执行必须路由到 sibling `knowledge-maintain` 的 revision-safe 更新流程，不在 Curate 中直接覆盖 Markdown。

普通 update 不得暗中执行 split、merge、supersede 或其他 identity-level 变化。需要改变对象身份结构时，必须另行形成明确的 identity-level 语义提案。

## 4. Relation Candidate

当用户明确提出正式关系意图，或当前 Agent 在知识整理中认为某个机器关系值得交给用户判断时，只能先形成 Relation Candidate：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py relation-propose \
  --vault <vault> \
  --source-id <knowledge-id> \
  --type <relation-type> \
  --target-id <knowledge-id> \
  --provenance <basis>
```

endpoint 也可以显式使用稳定外部引用，通过 `--source-external` / `--target-external` 与本地 identity 二选一。Candidate 返回精确的 source / type / target / provenance；对本地 Knowledge endpoint 还记录创建时实际读取到的 revision 与 Authority fingerprint。

Candidate 是治理记录，不是 Relation Record，也不是 Knowledge Object：它不进入 `objects`，不获得 Relation Record stable identity，不参与 typed relation traversal，也不产生 active Graph Projection。普通 wikilink、tag、全文共现或模型相似度不得自动创建 Candidate；Agent 必须把拟议关系作为待用户治理的候选展示，不得把 Candidate 描述为“关系已经建立”。

继续治理前可以重新检查 Candidate：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py relation-inspect \
  --vault <vault> \
  --candidate-id <candidate-id>
```

对本地 endpoint，检查会重新解析当前 Authority。若正文或其他会改变 Authority fingerprint 的内容已经变化，pending Candidate 确定性转为 `stale`；若只是 rename / move 且 fingerprint 不变，则 Candidate 继续保持 `pending`，并返回当前 locator / revision。不得因为 locator 变化本身把语义未变的 Candidate 作废。

用户明确拒绝 pending Candidate 时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py relation-reject \
  --vault <vault> \
  --candidate-id <candidate-id> \
  --confirmed-rejection
```

拒绝只改变 Candidate 的治理状态，不创建 Relation Record。

用户明确批准 pending Candidate 时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py relation-approve \
  --vault <vault> \
  --candidate-id <candidate-id> \
  --confirmed-approval
```

approval 会在同一受控事务中重新解析内部 endpoint；若 Authority fingerprint 已变化，则 Candidate 变为 `stale` 并拒绝写 Relation Authority。批准新的 triple 时创建独立 Relation Record stable identity 与 revision 1；相同 active source / type / target 已存在时不创建重复 relation，而是复用原 identity。新的 provenance 会补充到原 Relation Record 并推进 relation revision；完全重复的 provenance 只完成 Candidate 治理，不制造无意义 revision。

改变 source、type 或 target 必须通过新的 Candidate，并形成新的 relation 语义 identity；不得把已有 Relation Record 的 triple 原地改写成另一条关系。Relation approval 完成后，`knowledge-retrieve` 已有 traversal 可以立即只读消费该 Relation Record 及其全部 provenance。


## 5. 完成标准

新建知识资产的 Curate 只有在以下条件同时成立时完成：

- 用户已经看到并明确批准语义变更集；
- 新知识资产 Markdown 正文与批准文本一致，并通过 Human-readable Knowledge Writing Contract；
- 新对象 identity / revision / provenance 已建立；
- 依据材料仍然存在并可追溯；
- 确定性状态维护已完成且未扩张新的语义决定。
