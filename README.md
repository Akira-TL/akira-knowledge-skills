# Akira Knowledge Skills

`Akira-TL/akira-knowledge-skills` 是 Akira Knowledge 的 canonical source，用于维护长期知识管理相关的 Skill、文档与配套实现。

当前仓库只完成产品仓初始化，尚未发布可安装 Skill。计划中的 Primary Router 名称为 `akira-knowledge`；其对象模型、内部 Skill 边界与数据契约将在后续设计完成后再落地。

## 产品边界

Akira Knowledge 面向显式、持久、可检查、可更新和可复用的知识资产。

它与相邻产品保持明确边界：

- Akira Research 负责围绕科学未知建立、检验和更新证据；Knowledge 不接管科研状态机。
- Agent Context 负责当前任务工作上下文；Knowledge 不等同于会话上下文。
- 运行时 Memory 属于 Agent harness 的长期个性化机制；Knowledge 不作为其替代实现。

当一项信息已经形成值得长期保存、检索、更新和复用的知识时，才进入 Akira Knowledge 的职责范围。

## 当前状态

- Repository：已初始化。
- Product：Akira Knowledge。
- Planned Primary Router：`akira-knowledge`。
- Installable Skills：暂无。

在对象模型和 Skill ownership 明确之前，不把占位目录、临时脚本或未定协议描述为已发布能力。
