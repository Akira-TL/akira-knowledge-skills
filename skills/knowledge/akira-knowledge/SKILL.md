---
name: akira-knowledge
description: 管理显式、持久、可检查、可更新和可复用的长期知识；当前 0.1 实现从 Obsidian Vault bootstrap / registration 开始，并逐步路由 capture、curate、retrieve 与 maintain 工作流。
disable-model-invocation: true
---

# Akira Knowledge

`akira-knowledge` 是 Akira Knowledge 0.x 系列的主要用户入口。它只负责识别知识工作意图、检查前置条件、选择 owning 工作流和停止边界；共同 Authority、identity、revision、修改治理与持久化规则以仓库 `CONTEXT.md` 和 accepted ADR 为准，不在各工作流中复制第二套规则。

## 1. Existing Vault bootstrap

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

## 2. Registration contract

registration 原地完成：保留路径、正文、未知 Properties、tags、wikilinks、comments 与用户组织方式，只加入 Akira Knowledge 专用的稳定 identity / object kind，并建立 Vault 级配置和 SQLite registry / revision 基础。

Akira Knowledge 专用 Properties 当前为：

- `akira_knowledge_id`
- `akira_knowledge_kind`

它们属于 Knowledge-owned metadata。未注册 Markdown 若已经存在这些保留字段，必须 fail closed 并让用户显式处理冲突，不得静默接管其既有语义。

已有已注册对象再次执行 registration 时保持同一 identity；若检测到其人类 Authority 已经发生未同步修改，当前 bootstrap 命令停止，等待 revision-safe 更新工作流处理，不把 registration 当成覆盖入口。

## 3. 当前实现边界

本 Skill 当前实现 `0.1.x` 的 Vault bootstrap / registration 纵向切片。Capture、Curate、Retrieval 与长期维护属于同一 0.1 Spec 的后续实现票；这些能力尚未存在时，不得把缺失工作流伪装成已完成能力，也不得自行用临时 Markdown/SQLite 操作绕过其 owning Skill。

需要依赖 Vault 语义的 Obsidian 操作时复用既有 Obsidian 能力；Akira Knowledge 不创建第二套通用 Obsidian Skill。
