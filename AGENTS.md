# Repository instructions

本仓库是 `Akira-TL/akira-knowledge-skills` 的 canonical source，维护 Akira Knowledge 产品。0.x.x Wayfinder 已完成，当前按 `docs/roadmap/0x-series.md` 从 `0.1.x` 开始实现。已经落地的 Skill / script 只描述其真实完成的纵向切片；尚未完成的后续能力不得因路线图或 Spec 已存在就描述成已实现。

## 产品边界

Akira Knowledge 负责显式、持久、可检查、可更新和可复用的知识资产。0.x 系列的用户前端与知识浏览环境只规划 Obsidian；当前不设计第二套前端或可替换前端抽象。canonical 内容继续优先采用普通本地文件与可检查结构，以保证数据可控、可恢复和 Agent 安全操作，而不是为了同时兼容其他前端。

- Scientific Research 的 Research Question、Hypothesis、Design、Study、Dataset、Analysis、Interpretation 与 evidence provenance 继续由 Akira Research 拥有。
- 当前任务上下文由项目与 Agent harness 的 Context 机制拥有；Knowledge 不复制会话上下文。
- Agent harness 的 Memory 属于运行时个性化能力；Knowledge 不冒充或替代运行时 Memory。

0.x 系列的 Primary Router 为 `akira-knowledge`，主要用户入口保持单一。当前已确定的基础领域工作流按用户意图与知识生命周期拆为 `knowledge-capture`、`knowledge-curate`、`knowledge-retrieve`、`knowledge-maintain`；Skill 拥有行为契约而不拥有领域对象。后续 0.x 路线图只有在出现新的稳定用户意图或独立生命周期边界时才增加专业 Skill，不因新增对象、来源格式或实现技术机械拆分。需要 Obsidian Markdown、Bases、CLI 等通用操作能力时，Router 只声明复用 `kepano/obsidian-skills` 中对应 Skill；安装、加载与版本处理交给实际执行任务的 Agent 按现有 Skill 管理规则完成。本仓不重复建立 `knowledge-obsidian` 底层 Skill，只有后续确认上游能力存在明显且持续的问题时再另行决策是否自建。

## Skill 编写

后续增加 Skill 时：

- 每个稳定 Skill 只有一个 canonical `SKILL.md`，目录名与 frontmatter `name` 一致。
- 先确定 user-invoked 或 model-invoked，再编写触发条件和正文。
- Primary Router 只负责路由与 ownership，不复制专业 Skill 的方法正文。
- 多步骤流程使用可检查完成条件；分支材料按需放入 sibling references。
- 同一规则保持一个 source of truth；人类文档与 owning Skill 的稳定行为同步更新。

## 路线图

0.x 系列的能力版图、minor 版本切分、版本依赖与延期原则以 `docs/roadmap/0x-series.md` 为 canonical source。共同领域与治理规则仍以 `CONTEXT.md` 和 accepted ADR 为准；路线图不得重新定义这些共同基线。

## 仓库与发布

- `akira-knowledge` 已进入 `0.1.x` 实现，但在 0.1.x 发布门禁通过前不视为稳定发布；README 和用户回复不得生成未经发布流程确认的远端安装命令。
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
