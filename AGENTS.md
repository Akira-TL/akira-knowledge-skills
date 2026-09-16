# Repository instructions

本仓库是 `Akira-TL/akira-knowledge-skills` 的 canonical source，维护 Akira Knowledge 产品。当前只完成仓库初始化；在对象模型、数据契约与 Skill ownership 明确之前，不发布占位 Skill，也不把规划描述成已实现能力。

## 产品边界

Akira Knowledge 负责显式、持久、可检查、可更新和可复用的知识资产。v0.1 的唯一用户前端与知识浏览环境是 Obsidian；当前不设计第二套前端或可替换前端抽象。canonical 内容继续优先采用普通本地文件与可检查结构，以保证数据可控、可恢复和 Agent 安全操作，而不是为了同时兼容其他前端。

- Scientific Research 的 Research Question、Hypothesis、Design、Study、Dataset、Analysis、Interpretation 与 evidence provenance 继续由 Akira Research 拥有。
- 当前任务上下文由项目与 Agent harness 的 Context 机制拥有；Knowledge 不复制会话上下文。
- Agent harness 的 Memory 属于运行时个性化能力；Knowledge 不冒充或替代运行时 Memory。

计划中的 Primary Router 名称为 `akira-knowledge`。在用户确认核心对象模型之前，只保留该名称与产品边界，不提前固定 `Source`、`Note`、`Concept`、`Collection`、`Review` 等内部对象或 Skill。

## Skill 编写

后续增加 Skill 时：

- 每个稳定 Skill 只有一个 canonical `SKILL.md`，目录名与 frontmatter `name` 一致。
- 先确定 user-invoked 或 model-invoked，再编写触发条件和正文。
- Primary Router 只负责路由与 ownership，不复制专业 Skill 的方法正文。
- 多步骤流程使用可检查完成条件；分支材料按需放入 sibling references。
- 同一规则保持一个 source of truth；人类文档与 owning Skill 的稳定行为同步更新。

## 仓库与发布

- 当前仓库没有可安装 Skill，不得生成看似可执行的安装命令。
- 不默认添加 package metadata、CI、marketplace、release automation 或 License；这些都需要独立决策。
- 正式提交遵守 Akira 全局 Git 规则与 Guard 提交入口。
- 未来接入 Lattice 时，Lattice 只固定本仓 revision，不作为运行时 Skill source。

## Agent skills

### Issue tracker

本仓使用 GitHub Issues 作为 issue tracker。具体操作契约见 `docs/agents/issue-tracker.md`。

### Workflow roles

工作流角色直接使用 canonical 名称作为 GitHub labels。具体映射见 `docs/agents/triage-labels.md`。

### Domain docs

本仓采用 single-context domain layout；领域词汇使用根目录 `CONTEXT.md`，ADR 在首次需要时按 `docs/agents/domain.md` 约定建立。
