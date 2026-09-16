---
name: knowledge-curate
description: 把一个或多个材料记录整理成长期知识正文提案，或为既有知识资产形成普通更新提案；人类长期正文只有在用户明确批准后才成为 Authority。
---

# Knowledge Curate

`knowledge-curate` 负责整理、提炼与综合材料，并通过 proposal → explicit approval 的治理边界创建或修改长期知识。它不负责低摩擦 Capture，也不绕过 revision-safe 更新规则。

## 1. 形成提案

读取用户指定或当前工作流选定的一个或多个材料记录，由当前主模型直接形成拟长期保存的正文。提案必须是一个可独立理解、值得长期维护的知识单元；不得机械要求一条资产只包含一个 Claim 或 Concept。

把模型已经形成的候选正文写入 proposal store：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py curate-propose \
  --vault <vault> \
  --material-id <material-id> \
  --body-file <proposal-body-file>
```

为既有知识资产提出补充、纠错或适用边界修改时增加 `--target-id <knowledge-asset-id>`。proposal 是 candidate，不是人类内容 Authority；创建 proposal 不得改写目标知识 Markdown。

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

当前可以为既有知识资产生成 update proposal，但执行已批准 update 必须交给 revision-safe 更新工作流。该工作流尚未完成时 fail closed，不得为了“已经得到用户批准”而直接覆盖当前 Markdown。

普通 update 不得暗中执行 split、merge、supersede 或其他 identity-level 变化。需要改变对象身份结构时，必须另行形成明确的 identity-level 语义提案。

## 4. 完成标准

新建知识资产的 Curate 只有在以下条件同时成立时完成：

- 用户已经看到并明确批准语义变更集；
- 新知识资产 Markdown 正文与批准文本一致；
- 新对象 identity / revision / provenance 已建立；
- 依据材料仍然存在并可追溯；
- 确定性状态维护已完成且未扩张新的语义决定。
