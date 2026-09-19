---
name: knowledge-curate
description: 把材料整理成长期知识正文提案、为既有知识形成更新提案，并在 0.3.x 中形成受治理的关系候选（Relation Candidate）；候选内容只有在后续明确批准后才能成为 Authority。
---

# Knowledge Curate

`knowledge-curate` 负责整理、提炼与综合材料，并通过 proposal → explicit approval 的治理边界创建或修改长期知识；`0.3.x` 还由本 Skill 负责形成关系候选（Relation Candidate）并处理候选的检查 / 拒绝。它不负责低摩擦 Capture，也不绕过 revision-safe 更新规则，更不能把模型推断的关系直接写成 Relation Record Authority。

## 1. 形成提案

读取用户指定或当前工作流选定的一个或多个材料记录，由当前主模型直接形成拟长期保存的正文。提案必须是一个可独立理解、值得长期维护的知识单元；不得机械要求一条资产只包含一个 Claim 或 Concept。

把模型已经形成的候选正文写入 proposal store：

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

向用户展示拟批准的语义变更集：目标是新建还是更新、拟正文、依据材料，以及会发生的确定性 metadata / provenance / 状态维护。不得把 proposal 持久化本身描述成“知识已经更新”。

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

拒绝只改变 Candidate 的治理状态，不创建 Relation Record。Candidate approval / Relation Record 创建由 `0.3.x` 后续实现阶段闭合；对应能力完成前，不得用直接 SQLite 写入绕过治理。

## 5. 完成标准

新建知识资产的 Curate 只有在以下条件同时成立时完成：

- 用户已经看到并明确批准语义变更集；
- 新知识资产 Markdown 正文与批准文本一致；
- 新对象 identity / revision / provenance 已建立；
- 依据材料仍然存在并可追溯；
- 确定性状态维护已完成且未扩张新的语义决定。
