# Akira Knowledge 领域词汇

## 材料记录

表示真正进入 Knowledge 工作流、需要被暂存、整理、摘录、排队沉淀或记录处理状态的材料对象；单纯存在一个 URL、DOI 或外部对象标识符不会自动创建材料记录。材料记录与知识资产彼此独立，沉淀完成后也不因生成知识资产而自动删除。

## 知识资产

由用户长期阅读、维护和复用的正式知识内容。知识资产不强制原子化为单一 Claim 或单一 Concept，而应形成一个可独立理解、长期维护和复用的知识单元；一个知识资产可以综合多个材料记录，一个材料记录也可以支持多个知识资产。知识资产只有在形成可独立理解、值得长期维护的正文提案并经过用户批准后才进入正式长期知识；后续可被更新、回顾、退役或替代，但历史可追溯性不得通过静默删除来制造。

## 材料记录状态

材料记录只保留 `待处理` 与 `已处理` 两个主状态。整理、提炼、综合、回顾和更新属于行为，不是必须逐级经历的领域状态。`已处理` 的结果可以是支持一个或多个知识资产、仅保留作参考，或逻辑丢弃；逻辑丢弃默认只把材料移出正常检索与沉淀候选，不等同物理擦除。

## Knowledge 工作流入口

只有当用户表达持久化意图，或 Knowledge Skill 正在执行明确的捕获、整理、沉淀流程时，输入才进入 Knowledge 工作流并创建材料记录。普通工程、研究或对话任务中偶然出现的内容不会因为 Agent 判断“可能有用”而自动进入长期知识库。

## 单 Vault 总知识库与根路由

Akira Knowledge 默认维护一个长期总 Obsidian Vault，而不是按主题、知识类型或项目拆分多套数据库。一个 Vault 只拥有一套根级 `.akira-knowledge/knowledge.sqlite` 结构化 Authority；主题、学科、项目与用途通过目录、Properties、Relation、动态视图和根路由组织。只有真实的权限、ownership 或独立生命周期边界才构成另建 Vault 的理由，普通分类需求不构成拆库理由。

Vault 根目录的 `KNOWLEDGE.md` 是人类与 Agent 共用的顶层导航 Authority：它维护高层 Knowledge Map、稳定主题 / 项目入口与工程工作区约定，不复制每个 Knowledge Asset、SQLite registry 或 Relation Authority。Agent 进入该 Vault 后先读根 `KNOWLEDGE.md`，再选择相关主题或项目区域；精确知识查找继续使用 Retrieval Contract。根 `KNOWLEDGE.md` 不注册成普通 Knowledge Asset，也不由 Projection 自动覆盖。初始化在根 `AGENTS.md` 中维护 Akira Knowledge 自有指令块，要求 Agent 主动读取该路由，同时保留用户已有的其他 Agent 规则。

Knowledge Vault 同时允许承载代码、框架、实验实现、原型、展示、报告、可视化和其他长期可复用 artifact。初始化只提供 `收件箱/`、`系统/` 与 `.assets/` 三个最低公共入口，不强制创建“项目 / 知识 / 记录 / 成果”等横切 taxonomy。真正的一级内容目录应由用户根据稳定领域语义在 `KNOWLEDGE.md` 中定义，例如科研、公司与产品、技术、设计与创作、个人等；目录名本身承担第一层人类路由，不依赖 `00`–`99` 数字前缀。依赖树、虚拟环境、缓存、测试缓存、构建目录和可再生产物不是 Knowledge；`.git/`、`.obsidian/`、`.akira-knowledge/`、`node_modules/`、`.venv/`、常见 cache/build 目录以及 `AK Views/` / `AK Graph/` 等路径必须在扫描遍历阶段直接剪枝，也不得作为显式 registration 目标。

## 人类可读 Knowledge Asset 写作合同

Knowledge Asset 的 Markdown Authority 首先服务人长期阅读、搜索、链接和维护，不能退化为聊天记录、模型思考过程、一次性分析报告或材料摘要堆叠。新建与正文更新必须遵守 `akira-knowledge/references/human-readable-writing.md`；Capture 的原始材料记录除外，因为 Capture 必须保留用户原始输入。

共同原则如下：

- 一篇 Knowledge Asset 围绕一个稳定检索目标或高内聚知识单元组织；不机械要求“一条 Claim 一篇”，也不把多个可独立检索的问题塞进同一文档。
- 标题是主要人类检索句柄，必须具体、可搜索并能代表正文边界。稳定文件名应尽量与正式标题一致；旧名称、缩写和常用同义词进入 aliases。stable identity 不依赖标题或路径。
- 一级标题后直接进入定义、结论、用途、适用范围或核心问题。删除“本文将……”“下面首先……”“综上所述……”等不携带知识的生成式元话语。
- 一个普通段落表达一个完整意思并把重要信息前置；既避免墙状长段落，也避免连续大量单句段。句子优先短、完整、直接，专业术语可以复杂，句法不必复杂。
- 每篇资产恰好一个一级标题，标题层级连续；小节标题描述读者能找到的具体内容，不用“背景 / 分析 / 说明 / 总结”机械拼模板。
- 列表只表示真正并列或有顺序的信息，列表项保持平行结构；连续论述使用正常段落。表格用于多属性结构化比较，不承载长篇叙述。
- 普通 wikilink 只负责人类导航。正文应链接到拥有该知识的 Knowledge Asset，避免复制完整段落形成多份 Authority；typed relation 继续独立治理。
- 已核验事实、方法建议、构想和待核验内容必须区分。流畅语言不能掩盖 verification / review 状态。
- Curate 在 proposal 持久化前必须完成 Human-readable Writing Review；明确结构错误 fail closed，风格 finding 由主模型先解决再提交用户审批。Maintenance 修改正文时继续遵守同一合同，但不得以“统一格式”为由无关重写整篇 Authority。

完整的段落、句子、标题、列表、链接、不同知识类型默认骨架和自检规则以共享 reference 为准。

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

## 已有 Obsidian Vault 接入

已有 Obsidian Vault 默认原地接入，不要求复制到新的 Akira 专用 Vault。接入首先进行只读盘点，识别 Markdown、Properties、links、Bases、附件和现有目录结构；在用户明确 Knowledge 管理范围之前，不移动、重命名、改写正文、重排 frontmatter、批量改标签或重构目录。一个 Vault 可以长期同时包含 Knowledge-managed 内容与普通 Obsidian 内容，未注册 Markdown 不会仅因为存在于 Vault 中就自动成为材料记录或知识资产。

用户确认管理范围后，已有长期 Markdown 通过原地注册进入 Knowledge：保留原路径、正文、wikilink、Properties 与用户组织方式，只补充 Knowledge 必需且 ownership 已明确的最小机器 metadata，例如 stable identity 与 object kind。对一个已批准范围内的确定性 identity 注入可以批量执行，无需逐篇确认，但仍必须满足 round-trip safety。已有 Properties、tags 与 links 默认保留原语义，不因字段名相似或被 Knowledge 接入就自动映射为工作流状态、对象类别或 typed relation。

只有当内容当前不属于目标 Vault，而用户明确要求把它纳入目标 Vault 时，才属于 import；已有 Vault 的原地接管属于 bootstrap / registration，不是 import。0.x 后续 migration 只允许迁移 Akira Knowledge 自己拥有的 schema、字段、结构化 machine store 或可重建 Projection；版本升级不得借 migration 批量改写用户正文、标题、目录、普通链接或其他人类语义。新增索引、embedding、Bases、graph cache 或 relation type 应优先通过增量结构化扩展或 Projection 重建实现，避免反复迁移人类 Markdown。

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
