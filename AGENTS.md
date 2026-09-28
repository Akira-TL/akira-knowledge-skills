# Repository instructions

本仓库是 `Akira-TL/akira-knowledge-skills` 的 canonical source，维护 Akira Knowledge 产品。0.x.x Wayfinder 已完成；`0.1.x` 基础 Knowledge Loop 已实现并通过发布就绪黑盒门禁，后续继续按 `docs/roadmap/0x-series.md` 推进。已经落地的 Skill / script 只描述其真实完成的版本能力；尚未完成的后续能力不得因路线图或 Spec 已存在就描述成已实现。

## 产品边界

Akira Knowledge 负责显式、持久、可检查、可更新和可复用的知识资产。0.x 系列的用户前端与知识浏览环境只规划 Obsidian；当前不设计第二套前端或可替换前端抽象。canonical 内容继续优先采用普通本地文件与可检查结构，以保证数据可控、可恢复和 Agent 安全操作，而不是为了同时兼容其他前端。

- Scientific Research 的 Research Question、Hypothesis、Design、Study、Dataset、Analysis、Interpretation 与 evidence provenance 继续由 Akira Research 拥有。
- 当前任务上下文由项目与 Agent harness 的 Context 机制拥有；Knowledge 不复制会话上下文。
- Agent harness 的 Memory 属于运行时个性化能力；Knowledge 不冒充或替代运行时 Memory。

0.x 系列的 Primary Router 为 `akira-knowledge`，主要用户入口保持单一。当前已确定的基础领域工作流按用户意图与知识生命周期拆为 `knowledge-capture`、`knowledge-curate`、`knowledge-retrieve`、`knowledge-maintain`；Skill 拥有行为契约而不拥有领域对象。后续 0.x 路线图只有在出现新的稳定用户意图或独立生命周期边界时才增加专业 Skill，不因新增对象、来源格式或实现技术机械拆分。需要 Obsidian Markdown、Bases、CLI 等通用操作能力时，Router 只声明复用 `kepano/obsidian-skills` 中对应 Skill；安装、加载与版本处理交给实际执行任务的 Agent 按现有 Skill 管理规则完成。本仓不重复建立 `knowledge-obsidian` 底层 Skill，只有后续确认上游能力存在明显且持续的问题时再另行决策是否自建。

## 安装边界

Akira Knowledge 是项目级 / Vault 级专业工作流。`akira` Router 选择 `akira-tl/akira-knowledge-skills/akira-knowledge` 后，必须从目标知识项目或 Obsidian Vault 对应工作目录使用 Skiloom `--scope workspace` 安装；不得把 Knowledge suite 安装到用户级 `~/.agents/skills` 作为跨项目共享 runtime。当前尚未完成正式 GitHub Release，开发期使用显式 Git `main` source 不得被描述为稳定版本发布。

Knowledge 领域 Skill 的 dependency closure 由 `skiloom-package.toml` 解析。需要 Obsidian 通用能力时，第三方 Skill 默认跟随当前 Knowledge workspace Target；只有它被 Akira Catalog 独立定义为跨项目通用能力时才允许进入用户级 Target。

## Skill 编写

后续增加 Skill 时：

- 每个稳定 Skill 只有一个 canonical `SKILL.md`，目录名与 frontmatter `name` 一致。
- 每个 Skill 包维护 `skiloom-package.toml`，仓库发现范围由根目录 `skiloom-repo.toml` 定义；canonical `SKILL.md` 只使用标准 Agent Skill frontmatter，执行器专属调用策略留在对应 metadata 文件中。
- 先确定 user-invoked 或 model-invoked，再编写触发条件和正文。
- Primary Router 只负责路由与 ownership，不复制专业 Skill 的方法正文。
- 多步骤流程使用可检查完成条件；分支材料按需放入 sibling references。
- 同一规则保持一个 source of truth；人类文档与 owning Skill 的稳定行为同步更新。

## 路线图

0.x 系列的能力版图、minor 版本切分、版本依赖与延期原则以 `docs/roadmap/0x-series.md` 为 canonical source。共同领域与治理规则仍以 `CONTEXT.md` 和 accepted ADR 为准；路线图不得重新定义这些共同基线。

## 仓库与发布

- `akira-knowledge` 的 `0.1.x` 实现已通过发布就绪门禁，但尚未完成 GitHub tag / release；README 和用户回复不得把当前仓库状态描述成已经发布的稳定版本，也不得生成未经发布流程确认的远端安装命令。
- 当前已按明确决策维护 Skiloom Package metadata；它只描述标准 Skill 包、依赖与仓库发现范围，不授予 Registry、发布、安装或生命周期特权。CI、marketplace、release automation 与 License 仍需独立决策。
- 修改 Skill 或 Skiloom metadata 后，从本仓根目录运行 `skiloom validate . --json`；正式提交继续遵守 Akira 全局 Git 规则与 Guard 提交入口。
- 未来接入 Lattice 时，Lattice 只固定本仓 revision，不作为运行时 Skill source。

## Agent skills

### Issue tracker

本仓使用 GitHub Issues 作为 issue tracker。具体操作契约见 `docs/agents/issue-tracker.md`。

### Workflow roles

工作流角色直接使用 canonical 名称作为 GitHub labels。具体映射见 `docs/agents/triage-labels.md`。

### Domain docs

本仓采用 single-context domain layout；领域词汇使用根目录 `CONTEXT.md`，ADR 在首次需要时按 `docs/agents/domain.md` 约定建立。
