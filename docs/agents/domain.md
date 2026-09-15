# 领域文档

本文件规定工程 Skill 在探索与修改本仓时如何消费领域文档。

## 开始前读取

- 仓库根目录存在 `CONTEXT.md` 时，读取与当前工作相关的领域词汇。
- 若未来出现根目录 `CONTEXT-MAP.md`，则按其中指针读取相关上下文的 `CONTEXT.md`。
- 涉及已有架构决定时，读取与当前工作相关的 ADR。

上述文件尚不存在时直接继续，不把“缺少空白领域文档”本身当成问题，也不为了占位预先创建。由 `domain-modeling` 在真正形成已解决领域词汇或达到 ADR 门槛的决定时创建。

## ADR 约定

优先服从本仓已经存在的 ADR 位置、命名与模板。当前尚无既有约定，因此首次真正需要 ADR 时默认使用：

```text
docs/adr/NNNN-slug.md
```

编号按顺序递增，并采用 `domain-modeling` 的 ADR 格式。若未来仓库形成新的明确约定，应更新本文件，不建立并行的第二套 ADR 系统。

## 当前上下文布局

本仓当前采用 single-context layout：领域词汇的 canonical source 是根目录 `CONTEXT.md`。

示意结构：

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-example.md
│   └── 0002-example.md
└── ...
```

只有仓库未来真实出现多个独立领域上下文时，才引入 `CONTEXT-MAP.md` 和分上下文的 `CONTEXT.md`。

## 使用领域词汇

Issue title、设计讨论、重构提案、测试名称等涉及领域概念时，使用 `CONTEXT.md` 已确定的名称，不自行漂移到近义词或新造术语。

若当前需要的概念尚未进入 glossary，先判断是已有术语可以复用，还是确实存在领域语言缺口；真正需要新增或重命名时交给 `domain-modeling` 与用户确认后更新。

## ADR 冲突

若当前方案与已有 ADR 冲突，必须明确指出冲突并说明为何值得重新讨论，不得静默覆盖既有决定。
