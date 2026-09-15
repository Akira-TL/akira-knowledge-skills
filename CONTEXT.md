# Akira Knowledge 领域词汇

## 材料记录

表示真正进入 Knowledge 工作流、需要被暂存、整理、摘录、排队沉淀或记录处理状态的材料对象；单纯存在一个 URL、DOI 或外部对象标识符不会自动创建材料记录。材料记录与知识资产彼此独立，沉淀完成后也不因生成知识资产而自动删除。

## 知识资产

由用户长期阅读、维护和复用的正式知识内容。知识资产不强制原子化为单一 Claim 或单一 Concept，而应形成一个可独立理解、长期维护和复用的知识单元；一个知识资产可以综合多个材料记录，一个材料记录也可以支持多个知识资产。

## 关系记录

表示具有明确机器语义、会影响检索、推理、治理或 provenance 的 typed relation。关系端点可以是材料记录、知识资产，也可以是 Knowledge 外部对象的稳定引用；普通人类导航链接不自动形成关系记录，关系记录本身也不是用户需要维护的知识正文。

## 外部引用

用于指向由其他产品、系统或外部来源拥有的对象，可包含 owner / namespace、identifier、适用时的 revision 与 locator。外部引用是值类型而非独立领域实体，不因被 Knowledge 使用而取得被引用对象的 ownership。

## 权威来源（Authority）

表示某一逻辑语义唯一可直接编辑并决定其正式状态的来源。Authority 由语义职责而不是文件格式决定；同一逻辑内容不得同时存在两份可编辑 Authority。知识资产正文及用户主动维护的属性、导航链接属于人类内容 Authority；关系记录、材料记录的工作流状态、provenance / derivation lineage、精确外部引用及后续明确的治理或 revision 语义属于结构化 Authority。外部对象的事实与身份仍由其原 owner 持有 Authority。

## 派生投影（Projection）

表示从 Authority 或具有明确 lineage 的上游信息派生出的可重建表示，例如 Obsidian Bases、全文索引、embedding、graph cache、ranking 和 generated context view。Projection 可以持久化，也可以通过明确映射的界面操作请求修改对应 Authority，但其自身不得成为第二套可编辑真相；丢失或过期 Projection 不得造成 canonical knowledge 丢失。
