---
name: knowledge-capture
description: 处理用户明确要求长期保存的信息，把它作为材料记录进入 Akira Knowledge 工作流；保留原始 capture note、Source 引用与 provenance，不把普通任务上下文自动持久化。
---

# Knowledge Capture

`knowledge-capture` 只负责低摩擦捕获并创建材料记录。它不负责把材料直接改写成长期知识资产；整理、提炼和综合由 `knowledge-curate` 拥有。

## 1. 进入条件

只有以下情况可以创建材料记录：

- 用户明确表达长期保存意图，例如“保存这个”“记下来”“加入我的知识库”；
- 当前已经由用户进入显式 Knowledge capture 流程，并且本次输入明确属于该流程。

普通问答、软件工程、科研、写作或其他任务中偶然出现的信息，即使 Agent 判断“以后可能有用”，也不能自动 Capture。无法确认持久化意图时保持当前任务上下文，不调用写入命令。

## 2. 捕获

先确认目标 Vault 已完成 `akira-knowledge` bootstrap。随后调用已加载的 `akira-knowledge` 共享确定性工具执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py capture \
  --vault <vault> \
  --confirmed-intent \
  --note <original-user-capture-note> \
  --source <optional-source-locator>
```

长文本可以使用 `--note-file` 替代 `--note`。`--source` 可以重复；Source 可以是 URL、DOI、本地 artifact locator 或其他外部引用 locator。Source identity 继续由原 owner 持有，不能拿 Source locator 当作材料记录 identity。

## 3. 写入边界

每次显式 Capture 都创建新的材料记录，并得到独立 UUIDv7 identity、初始 revision、`material_record` 对象类别与 `待处理` 状态。即使 Source locator 相同，也不得自动合并两个 Capture；工具可以返回去重候选供后续判断，但不会执行语义 merge。

材料 Markdown 的正文就是用户原始 capture note。Capture 阶段不得自动把模型生成的摘要、标签、解释、关系或冲突判断写进人类内容 Authority。Source locator、capture 时间和确定性 provenance 保存在结构化 Authority 中。

新材料写入用户已经批准的默认写入根；如果 Vault 尚未 bootstrap、配置越界、结构化 Authority store 缺失或写入前提不成立，必须 fail closed。

## 4. 完成标准

一次 Capture 只有在以下条件同时成立时完成：

- Obsidian 中出现一个可读材料记录 Markdown；
- identity、revision、对象类别和 `待处理` 状态已经建立；
- 原始 capture note 未被模型改写；
- Source 与 capture provenance 已进入结构化 Authority；
- 相同 Source 的已有材料仅作为候选返回，不发生自动 merge。
