# Akira Knowledge Skills

`Akira-TL/akira-knowledge-skills` 是 Akira Knowledge 的 canonical source，用于维护长期知识管理相关的 Skill、文档与配套实现。

0.x.x 产品规划已经完成，`0.1.x` 基础 Knowledge Loop 与 `0.2.x` Retrieval + Views 均已实现并通过发布就绪黑盒门禁。Primary Router 为 `akira-knowledge`；当前实现尚未执行 GitHub tag / release，因此不等同于已经发布的稳定版本。

## 产品边界

Akira Knowledge 面向显式、持久、可检查、可更新和可复用的知识资产。

它与相邻产品保持明确边界：

- Akira Research 负责围绕科学未知建立、检验和更新证据；Knowledge 不接管科研状态机。
- Agent Context 负责当前任务工作上下文；Knowledge 不等同于会话上下文。
- 运行时 Memory 属于 Agent harness 的长期个性化机制；Knowledge 不作为其替代实现。

当一项信息已经形成值得长期保存、检索、更新和复用的知识时，才进入 Akira Knowledge 的职责范围。

## 当前状态

- Product：Akira Knowledge。
- Primary Router：`akira-knowledge`。
- 0.x Wayfinder：已完成。
- 0.1.x：实现完成，发布就绪门禁已通过。
- 0.2.x：实现完成，独立黑盒与升级兼容门禁已通过。
- 0.3.x：实现中；已完成 Relation Candidate 治理、明确 approval、Relation Record triple 去重与 provenance 增补，后续继续实现显式撤回、Graph Projection 与完整 Knowledge Network 闭环。
- 当前已实现：Vault 只读盘点、管理范围批准后的原地 registration、UUIDv7 identity、Knowledge-owned Properties、Vault 配置与 SQLite registry / revision 基础、显式 Capture 到材料记录、Curate 的 proposal → approval、新建知识资产、Exact / Filter / Full-text 基础 Retrieval、既有知识 revision-safe update、显式 Retrieval Scope、按 stable identity 去重并保留多路径命中依据的任务相关知识集合、Relation Candidate 治理与 endpoint 陈旧保护、用户明确 approval 后的 Relation Record Authority 创建、同 triple 去重与 provenance 增补，以及可删除重建且不拥有 Authority 的 Obsidian Bases 动态视图。
- 发布状态：尚未创建 GitHub tag / release，也未执行远端安装发布。

## Development

运行当前黑盒测试：

```bash
./scripts/check.sh
```

发布就绪验收证据见 [`docs/validation/0.1-release-gate.md`](docs/validation/0.1-release-gate.md) 与 [`docs/validation/0.2-release-gate.md`](docs/validation/0.2-release-gate.md)。在实际 GitHub tag / release 完成前，不把当前实现描述为已经发布的稳定版本，也不生成未经发布流程确认的远端安装命令。
