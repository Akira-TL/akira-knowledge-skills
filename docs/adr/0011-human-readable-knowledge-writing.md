---
status: accepted
---

# 人类可读 Knowledge Asset 写作合同

Akira Knowledge 的 Markdown Authority 首先是给人长期阅读、搜索和维护的知识文档，其次才是机器可处理文本。Knowledge Asset 不得退化为聊天记录、模型思考过程、一次性分析报告或材料摘要堆叠。

创建或更新 Knowledge Asset 时，正文必须满足共享的 Human-readable Knowledge Writing Contract。完整操作规范位于 `akira-knowledge/references/human-readable-writing.md`；本 ADR 冻结以下产品边界：

1. 一篇 Knowledge Asset 围绕一个稳定检索目标或高内聚知识单元组织。系统不要求“一条 Claim 一篇”，也不允许以“大而全”为理由把多个独立问题塞进同一资产。
2. 标题是主要人类检索句柄，应具体、可搜索并代表正文边界。稳定文件名应尽量与正式标题一致，历史名称和缩写进入 aliases；stable identity 不依赖路径或标题。
3. 正文开头优先给定义、答案、用途或适用范围，不保留无信息量的生成式铺垫。普通段落一段一个意思，重要信息前置；既避免墙状长段落，也避免连续碎片化单句段。
4. 标题层级用于导航。每篇资产只有一个一级标题，层级连续；小节标题应描述可检索内容，不以“背景 / 分析 / 说明 / 总结”等泛化模板机械搭框架。
5. 列表仅用于真正并列或有顺序的信息，表格用于结构化比较。连续论述保持正常段落，不把整篇正文转成 bullet 列表。
6. 普通 wikilink 服务人类导航，不因为写作链接自动产生 typed relation。内容应链接到 owning Knowledge Asset，避免复制完整知识造成多份 Authority。
7. 事实、方法建议、构想和待核验内容必须区分。流畅语言不得掩盖证据状态；review / verification 等现有语义继续保留。
8. Capture 不执行本合同的润色要求，因为材料记录必须保留原始用户 capture note。合同从 Curate 形成长期正文 proposal 开始生效。
9. Curate 在 proposal 持久化前必须完成写作自检。确定性检查器可以 fail closed 于明确结构错误，并返回风格 findings；主模型不得把存在明显 findings 的草稿直接交给用户批准。
10. Maintenance 对正文更新继续遵守 revision-safe 治理，同时不得借“统一格式”无关重写整个 Authority。只修改批准的语义范围，并在触及段落时维持或改善其可读性。
11. 写作合同是正文质量合同，不是事实验证器。它不能替代 Source Review、verification、Relation governance 或科研论证。

该合同借鉴 Evergreen Notes、Zettelkasten、Dendron、Obsidian、Google / Microsoft 技术写作规范以及 PARA / Progressive Summarization 中与未来检索、人类扫描和可维护性有关的实践，但不采用任何一个外部系统的数据模型或固定 taxonomy。
