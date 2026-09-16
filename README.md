# Akira Knowledge Skills

`Akira-TL/akira-knowledge-skills` 是 Akira Knowledge 的 canonical source，用于维护长期知识管理相关的 Skill、文档与配套实现。

0.x.x 产品规划已经完成，当前从 `0.1.x` 开始实现。Primary Router 为 `akira-knowledge`；首个已实现纵向切片是 Obsidian Vault 的只读 bootstrap 与经用户批准后的原地 registration。0.1.x 尚未通过最终发布门禁，因此当前实现不等同于稳定发布版本。

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
- 0.1.x：实现中。
- 当前已实现：Vault 只读盘点、管理范围批准后的原地 registration、UUIDv7 identity、Knowledge-owned Properties、Vault 配置与 SQLite registry / revision 基础，以及显式 Capture 到材料记录。
- 当前尚未完成：Curate、Retrieval、revision-safe update 与最终 0.1.x 黑盒发布门禁。

## Development

运行当前黑盒测试：

```bash
./scripts/check.sh
```

在 0.1.x 发布门禁通过前，不把本地实现描述为稳定发布能力，也不生成未经发布流程确认的远端安装命令。
