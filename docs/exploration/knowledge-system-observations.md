# Knowledge System 探索记录

> 状态：探索材料（非设计决策）
>
> 本文件只保存当前阶段已经观察到的思路、外部产品特性和待后续讨论的问题。除非后续形成正式设计并迁移到对应规范，否则这里的内容不得视为 Akira Knowledge 的对象模型、数据契约或 Skill 边界。

## 1. FLO.W / Notion 观察

来源：

- <https://21notion.com/docs>
- <https://21notion.com/blog/notion-7-year-reflection>

### 1.1 少量稳定对象，而不是按场景不断增加容器

FLO.W 值得保留的核心思想不是其 Notion 模板本身，而是：使用较少、稳定的信息对象承载多种工作场景，再通过关系、属性和视图形成不同入口。

这意味着 Akira Knowledge 后续不宜因为出现一种输入材料或使用场景，就机械新增一个对象或一个 Skill。例如网页、书籍、论文、想法、会议记录、日记等是否应成为独立对象或 Skill，需要由其语义和生命周期决定，而不是由来源格式决定。

### 1.2 关系和使用上下文比唯一分类更重要

传统文件夹或标签强调“这条信息属于哪里”；FLO.W 更有价值的方向是“这条信息可以支持什么行动、项目、问题或领域”。

对 Agent 而言，同一知识资产可能同时服务于多个上下文，因此目录更适合作为物理存储结构，语义关系和当前调用上下文更可能承担知识组织职责。

### 1.3 低摩擦捕获与长期知识应分开

输入阶段不应强迫用户立即决定完整分类、对象类型和长期位置。允许 Inbox / Quick Capture 一类暂存层存在，再由后续整理过程判断是否升级、合并、关联或丢弃。

因此目前保留一个重要候选区分：

```text
Capture / Inbox
    ↓
整理、判断、提炼
    ↓
长期 Knowledge Asset
```

这只是生命周期观察，尚未确定对象名称或数据结构。

### 1.4 Review 是知识形成与更新过程

原始记录本身不自动等于长期知识。周期性 Review 的价值包括：从记录中提炼可复用认识、发现冲突与陈旧信息、更新旧知识，而不是无限追加新笔记。

当前可继续观察的生命周期行为包括：Capture、Curate、Synthesize、Relate、Retrieve、Apply、Review、Update / Reconcile。它们现在只是行为维度，不是已确定的 Skill 列表。

### 1.5 Skill 不应机械对应数据库对象

一个暂时较强的设计假设是：对象属于 Knowledge 数据模型；Skill 更适合围绕用户意图和知识生命周期组织，而不是为每张“表”或每种对象各做一个 Skill。

因此当前仓库继续保持“不提前固定 Source、Note、Concept、Collection、Review 等对象或 Skill”的边界。

### 1.6 Knowledge 不应吞并相邻产品的 ownership

Task、Project、Research Question、Dataset、代码仓库、Person 等可以与知识资产建立关系，但并不因此自动成为 Akira Knowledge 自己拥有的对象。

尤其需要继续维持：

- Akira Research 负责科研状态机、Evidence provenance 及科学对象；
- 当前任务上下文由项目和 Agent harness 的 Context 机制负责；
- Agent Memory 属于运行时个性化能力；
- Knowledge 更偏向显式、持久、可检查、可更新和可复用的知识资产。

### 1.7 动态视图比固定入口更值得重视

FLO.W 的视图思想可以转换为 Agent 场景中的“Relevant Knowledge View”：不把整个知识库塞入当前上下文，而是根据当前 Intent、Project、Question 或其他关系构造相关知识集合，再提供给 Agent 使用。

长期来看，Knowledge 产品的高价值能力可能不只是“存进去”，而是“在正确场景召回正确的长期知识”。

---

## 2. Obsidian 初步观察

来源：Obsidian 官方文档及用户提供的两段教程视频。本节仍然只是产品能力观察，不代表已选择具体架构。

官方资料：

- <https://obsidian.md/help/data-storage>
- <https://obsidian.md/help/properties>
- <https://obsidian.md/help/links>
- <https://obsidian.md/help/bases>
- <https://obsidian.md/help/cli>
- <https://obsidian.md/help/community-plugins>

### 2.1 本地文件模型非常符合“本地、可控、Agent 可操作”的方向

Obsidian Vault 本质上是本地文件系统中的目录。正文笔记保存为 Markdown 纯文本文件，外部编辑器或程序直接修改文件后，Obsidian 会刷新 Vault 以反映变化。

这意味着 Obsidian 可以更多承担“人类交互界面与知识浏览器”的角色，而不必成为唯一的数据持有者。Agent 可以直接处理可审计的本地文件，同时保留 Obsidian 的可视化和交互体验。

### 2.2 Markdown + YAML frontmatter 提供了较好的机器可读基础

Obsidian 的 Properties 存储在 Markdown 文件顶部的 YAML frontmatter 中，适合保存小型、原子的结构化信息。正文继续保持普通 Markdown，可同时面向人和 Agent。

需要后续讨论的不是“要不要有属性”，而是哪些字段真正属于稳定知识契约，避免把 frontmatter 变成无限增长的半结构化数据库。

### 2.3 Links / Backlinks 可作为显式关系的一部分，但不能直接等同完整语义图

Obsidian 支持内部链接、反向链接、标题链接及文件间导航；文件重命名时还可以自动更新内部链接。

这对显式关系很有价值，但普通 `[[link]]` 只表达“存在链接”，不自动说明关系类型、方向语义或证据含义。因此后续若 Akira Knowledge 需要更严格的 typed relation，不能只把所有关系压缩成无类型双链。

### 2.4 Bases 很适合实现“同一批知识，多种动态视图”

Obsidian Bases 是核心插件。它基于现有本地文件及其 Properties 建立类似数据库的筛选、排序、分组和多视图展示；数据本身仍保存在本地 Markdown / Properties 中，视图定义保存在 `.base` 文件或 Markdown 中的 Base 代码块。

这一点与 FLO.W 的“少量稳定对象 + 动态视图”思路高度相容：不必为了新的使用场景复制一套数据，只需要形成新的查询和视图。

### 2.5 官方 Obsidian CLI 显著提高了 Agent 集成价值

当前官方 Obsidian CLI 可以从终端执行读取、创建、追加、移动、重命名、搜索、属性读写、链接/反向链接查询、未解析链接检查、孤立笔记检查、Base 查询以及插件管理等操作。

尤其值得后续评估的是：

- `move` / `rename` 可按 Vault 设置同步更新内部链接；
- `backlinks`、`links`、`unresolved`、`orphans`、`deadends` 可以用于知识图结构检查；
- `properties` / `property:set` / `property:read` 可操作结构化属性；
- `base:query` 可以把 Obsidian 视图作为机器可查询接口；
- Agent 不必所有操作都退化成自行编写一次性脚本或直接字符串改写 Markdown。

官方文档当前要求使用 Obsidian 1.12 系列的新安装器并在设置中启用 Command line interface；具体版本依赖应在真正实现时重新核验。

### 2.6 Community Plugins 应视为扩展层，而不是默认数据基础

Obsidian 社区插件可以扩展格式和能力，但插件会以第三方代码形式运行，并需要关闭 Restricted Mode 才能使用。后续如果 Akira Knowledge 依赖插件，应区分：

- 数据是否仍可脱离插件读取；
- 插件失效后知识资产是否仍然完整；
- 插件是否只是 UI / workflow 增强，而不是核心数据契约的唯一实现。

目前更倾向继续观察“核心数据保持普通本地文件，插件只是可替换增强层”这一原则，但尚未定案。

### 2.7 用户提供教程中的方向与上述判断基本一致

两段教程并非简单重复：从画面内容看，一段主要解释“AI 时代为什么重新看 Obsidian”与整个课程路线，另一段主要演示安装、Vault、界面和推荐设置。

教程给出的路线尤其值得记录：

```text
Level 1：建立资料库
- 建立结构与笔记
- 使用 Markdown / 双链等基础能力

Level 2：让 Agent 接管资料库
- Agent 整理资料库结构
- Agent 整理、发现链接
- Agent 撰写、修改笔记
- Agent 整理 frontmatter 属性

Level 3：形成工作流
- 让知识库参与持续的记录、整理、回顾和输出
```

教程后续课程还明确安排了“准备 Agent”“Obsidian CLI 与 Skill”“接管资料库”等主题。这与 Akira Knowledge 计划做成 Skill 产品族的方向存在直接关联，后续值得继续看，但当前不据此确定实现方案。

---

## 3. 暂不回答、留待正式设计阶段的问题

以下问题已经出现，但当前阶段不提前讨论或定案：

- Akira Knowledge 的最小核心对象到底是什么；
- Capture 是否是对象、状态还是独立输入层；
- typed relation 应如何表达，哪些关系直接用 Obsidian links，哪些需要结构化字段；
- Markdown / YAML / `.base` / 其他索引文件各自的 canonical ownership；
- Obsidian 是否只是默认前端，还是产品契约的一部分；
- Agent 直接编辑文件与通过 Obsidian CLI 操作的边界；
- 是否需要本地索引、全文检索、向量检索或其他派生数据层；
- 如何与 Akira Research、工程项目、运行时 Context / Memory 建立跨产品引用；
- 最终有哪些 Skill、各自按什么需求打包和安装。
