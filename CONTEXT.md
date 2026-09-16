# Akira Knowledge 领域词汇

## 材料记录

表示真正进入 Knowledge 工作流、需要被暂存、整理、摘录、排队沉淀或记录处理状态的材料对象；单纯存在一个 URL、DOI 或外部对象标识符不会自动创建材料记录。材料记录与知识资产彼此独立，沉淀完成后也不因生成知识资产而自动删除。

## 知识资产

由用户长期阅读、维护和复用的正式知识内容。知识资产不强制原子化为单一 Claim 或单一 Concept，而应形成一个可独立理解、长期维护和复用的知识单元；一个知识资产可以综合多个材料记录，一个材料记录也可以支持多个知识资产。知识资产只有在形成可独立理解、值得长期维护的正文提案并经过用户批准后才进入正式长期知识；后续可被更新、回顾、退役或替代，但历史可追溯性不得通过静默删除来制造。

## 材料记录状态

材料记录只保留 `待处理` 与 `已处理` 两个主状态。整理、提炼、综合、回顾和更新属于行为，不是必须逐级经历的领域状态。`已处理` 的结果可以是支持一个或多个知识资产、仅保留作参考，或逻辑丢弃；逻辑丢弃默认只把材料移出正常检索与沉淀候选，不等同物理擦除。

## Knowledge 工作流入口

只有当用户表达持久化意图，或 Knowledge Skill 正在执行明确的捕获、整理、沉淀流程时，输入才进入 Knowledge 工作流并创建材料记录。普通工程、研究或对话任务中偶然出现的内容不会因为 Agent 判断“可能有用”而自动进入长期知识库。

## 导航链接

表示由用户在人类可读内容中主动维护、主要用于阅读跳转与知识浏览的普通链接。导航链接只承诺存在人类导航关联，不自动表达关系类型、方向、因果、支持、冲突或 provenance 等机器语义，也不因存在 backlink 而获得反向关系语义。

## 关系记录

表示机器必须可靠理解的 typed relation，只有当明确关系语义会影响检索、推理、治理、provenance 或自动检查时才建立。关系记录至少包含 `source`、`type`、`target` 与 `provenance`；底层按有方向关系定义，对称性属于具体 relation type 的语义。关系端点可以是材料记录、知识资产，也可以是 Knowledge 外部对象的稳定引用。普通导航链接不自动升级为关系记录，关系记录也不要求自动镜像成人类链接；0.x 系列共同冻结 relation 机制，不预先冻结大规模 relation ontology，具体 relation type 可以在后续版本出现真实需要时再增加。模型推断出的 relation 必须先作为 candidate，经治理后才能成为结构化 Authority。

## 外部引用

用于指向由其他产品、系统或外部来源拥有的对象，可包含 owner / namespace、identifier、适用时的 revision 与 locator。外部引用是值类型而非独立领域实体，不因被 Knowledge 使用而取得被引用对象的 ownership。

## 稳定 identity 与 revision

材料记录、知识资产与关系记录都拥有独立于文件路径、文件名、标题和 Obsidian wikilink 文本的稳定机器 identity。rename、move 与普通标题修改不会创建新对象；它们只更新当前 locator、可读属性与对象 revision。每次 canonical Authority 成功发生变化时，对象当前 revision 都必须变化；Projection 重建、全文索引刷新、embedding 重算或 Graph View Projection 重建不得改变 Authority revision。revision 用于精确状态识别与 stale-write 检测，不等同于面向人的长期历史版本。

有语义意义的 Authority 变化必须保持长期可追溯性，至少能够说明原状态、修改原因、发生时间、依据与批准来源；由已批准操作必然引出的纯机械配套维护只需保留必要审计，不需要逐项制造面向人的历史版本。只要仍是同一个可独立理解的知识单元，正常更新、补充、纠错或适用边界变化保持原 identity 并产生新 revision；split、真正的 merge 或以新的长期知识单元替代旧单元属于 identity 级变化，必须经过既有用户批准治理。退役或被替代对象的旧 identity 默认永久保留且不得复用，除非用户明确要求物理删除并且删除语义要求不保留 tombstone。

关系记录的 identity 表示一个具体语义关系；改变 `source`、`type` 或 `target` 通常意味着结束旧 relation 并创建新的 relation identity，而 provenance 补充或治理状态变化可以在同一 identity 上产生新 revision。材料记录 identity 表示材料进入 Knowledge 工作流及其 Knowledge 自有处理状态，不等于 URL、DOI、文件哈希或其他 Source identity；外部对象的 revision 仍由原 owner 管理，Knowledge 只保存必要的外部引用。Obsidian 人类导航继续使用 wikilink，但机器语义必须解析回稳定 identity；文件移动、重命名或 Graph Projection 重建不能改变对象身份。

## 权威来源（Authority）

表示某一逻辑语义唯一可直接编辑并决定其正式状态的来源。Authority 由语义职责而不是文件格式决定；同一逻辑内容不得同时存在两份可编辑 Authority。知识资产正文及用户主动维护的属性、导航链接属于人类内容 Authority；关系记录、材料记录的工作流状态、provenance / derivation lineage、精确外部引用及后续明确的治理或 revision 语义属于结构化 Authority。外部对象的事实与身份仍由其原 owner 持有 Authority。

## 持久化布局约束

知识资产的长期人类可读正文直接以 Obsidian Markdown 正文作为 Authority，不在 SQLite 或其他机器存储中维护第二份可独立编辑的正文真相。真正进入 Knowledge 工作流的材料记录也默认具有可在 Obsidian 中阅读和链接的 Markdown 节点；原始 PDF、网页、文件或其他 Source artifact 保持其原有身份，材料节点只保存 Knowledge 自己的 capture / workflow 语义与必要引用。

YAML frontmatter / Obsidian Properties 只承担适合与单篇 Markdown 共同存在的小型、原子属性，例如稳定 identity、对象类别、标题/别名、用户标签，以及经字段 ownership 明确定义的少量对象状态或引用。frontmatter 不承担大段 provenance、全量 typed relation、长期 revision history、embedding、graph cache 或其他高密度机器状态。具体字段名和字段分配留给 Spec，但每一项语义只能指定一个 Authority；如果同一值也出现在其他存储中，其他副本只能是 Projection。

跨对象且需要可靠查询的结构化 Authority 默认进入一个本地 SQLite machine store，包括 typed relation、provenance / derivation lineage、语义 history / revision metadata、必要审计和其他明确属于结构化 Authority 的机器语义。SQLite 不拥有知识正文，也不把 Markdown 变成数据库渲染结果。0.x 默认不为每篇 Markdown 建立配套 `.json` / `.yaml` sidecar；只有未来某类 artifact 出现独立且充分理由时才另行决策。Git 可以用于 backup、diff、recovery 与仓库 history，但不作为 Knowledge 领域 revision/history 的唯一 Authority。

Obsidian Bases、全文索引、embedding、graph cache、ranking 以及为了 Graph View 生成的机器 Markdown 节点都属于 Projection。机器可视化 Markdown 应处于明确的 generated / Projection 区域并允许整批删除后从 Authority 重建。具体目录名、SQLite 路径、schema、字段名和 migration 机制由后续 Spec / 版本规划确定，不改变上述 ownership 约束。

## 派生投影（Projection）

表示从 Authority 或具有明确 lineage 的上游信息派生出的可重建表示，例如 Obsidian Bases、全文索引、embedding、graph cache、ranking、generated context view，以及为了 Obsidian 图谱可视化而生成的机器可视化 Markdown 节点。Projection 可以持久化，也可以通过明确映射的界面操作请求修改对应 Authority，但其自身不得成为第二套可编辑真相；丢失或过期 Projection 不得造成 canonical knowledge 丢失。

## Obsidian 0.x 前端边界

Akira Knowledge 0.x 系列只规划 Obsidian 作为用户前端与知识浏览环境，当前不为第二套前端设计可替换 Adapter 抽象。Knowledge Skill 使用领域操作表达读取、修改、移动、重命名、属性维护、链接检查与视图查询；具体执行优先利用 Obsidian 官方 CLI 处理依赖 Vault 语义的操作，在满足 round-trip safety 且不依赖 Obsidian 特有语义时可以直接操作本地文件。CLI 不可用时，只有存在经过验证的语义等价 fallback 才继续执行，否则 fail closed；这不改变 canonical 内容应保持可检查、可恢复的本地表示这一要求。

## 机器可视化 Markdown 节点

表示为了让 Agent / 机器层内容进入 Obsidian Graph View 而生成的 Markdown Projection。该节点可以使用普通 wikilink 连接到人类可读知识资产或其他可视化节点，使用户能够在图谱中观察机器内容与人类知识的关联；这些链接和节点默认属于可重建 Projection，不因出现在 Graph View 中而自动成为知识资产、人类内容 Authority 或正式 typed relation。只有底层对应语义已经通过既有治理成为 Authority 时，Projection 才展示该 Authority，而不是替代它。

## Retrieval Contract

Akira Knowledge 的基础检索能力不依赖向量数据库、知识图谱或 rerank，最低保证包括按稳定 identity 精确读取、按对象类型/状态/authoritative property 过滤、全文检索，以及沿正式 typed relation 的有方向扩展。默认长期知识检索以当前有效知识资产为范围；材料记录、退役知识、逻辑丢弃材料和历史 revision 只有在调用方显式要求时加入。每个结果至少返回 stable identity、object kind、canonical locator、matched evidence 与 retrieval reason；Contract 不定义跨 backend 的统一 relevance score。

向量检索、graph ranking、rerank 与任务相关知识集合都属于可选、可重建 Projection。它们可以改变候选召回或排序，但不能据相似度、排名或被召回这一事实自动创建知识、修改 Authority 或升级为 typed relation。Projection 过期或损坏时应显式降级到仍可用的基础检索能力，不能把已知过期结果静默冒充当前结果，也不能阻止直接访问 canonical knowledge。该检索契约由 Akira Knowledge 自身需求定义；ContextD 等外部项目仅可作为设计参考，不构成其架构模板、接口来源、backend 或数据模型约束。

## 修改治理

人类内容 Authority 的语义增删改必须先向用户展示拟变更范围并取得明确批准；用户批准的是一个明确的语义变更集，不是逐文件授权。已批准操作必然导致、且可以机械证明不改变语义的配套维护可以自动执行，但不得借机扩张修改范围。结构化 Authority 中，由真实操作、明确用户动作或确定性流程产生的 provenance、lineage、材料状态等可以自动维护；模型推断出的标签、关系、冲突或适用性判断必须先作为 candidate / Projection，经相应治理后才能升级为 Authority。

## Round-trip safety 与冲突处理

对 Markdown、YAML 或其他人类可编辑表示的修改必须最小化并保持 round-trip safety：保留未知字段、无关正文、用户格式偏好、链接与注释，不得为了修改一个字段而无关地重排或重写整份文件。Authority 与 Projection 漂移时按 ownership 解决，不采用 last-write-wins；Projection 应由 Authority 重建。若用户直接修改了并非该位置拥有的结构化镜像字段，应把变化解释为修改请求或检测为 drift，而不是静默接管 Authority。执行已批准变更前必须重新读取相关 Authority；若批准依据之后出现可能冲突的修改，必须 fail closed 并重新生成提案，只有可机械证明互不相交的变化才能继续执行。
