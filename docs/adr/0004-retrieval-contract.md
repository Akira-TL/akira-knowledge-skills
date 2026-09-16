---
status: accepted
---

# Retrieval Contract 独立于检索 backend

Akira Knowledge 0.x 系列把稳定 identity 精确读取、authoritative property 过滤、全文检索与正式 typed relation 扩展定义为共同基础检索能力，并要求这些能力在没有向量数据库、知识图谱和 rerank 的情况下仍可工作。检索结果必须能够重新定位到 canonical Authority，并说明实际命中依据与召回原因；不同 backend 的分数不被包装成统一产品级 relevance score。向量检索、graph ranking、rerank 和任务相关知识集合均属于可替换、可重建 Projection，它们可以在后续 0.x 版本按真实需求进入路线图以增强召回与排序，但不能因相似度、排名或召回结果自动创建知识或正式关系。Projection 失效时系统应显式降级到仍可用的基础检索能力，而不是阻断 canonical knowledge 的访问或静默返回已知过期结果。

这项决策来自 Akira Knowledge 自身的长期知识检索需求。ContextD 及其他外部系统中的类似思想仅具有参考价值，不构成 Akira Knowledge 的架构模板、接口来源、backend、对象模型或数据模型约束。
