---
status: accepted
---

# 导航链接与 typed relation 分层

Akira Knowledge 区分人类导航链接与机器可计算的 typed relation。普通 `[[link]]` 只负责人类阅读跳转，不自动承诺关系类型、方向、因果、支持、冲突或 provenance，也不因 backlink 获得反向语义；只有当某个明确关系会影响检索、推理、治理、provenance 或自动检查时，才建立关系记录。关系记录至少包含 `source`、`type`、`target` 与 `provenance`，底层统一按有方向关系定义，对称性由具体 relation type 声明。v0.1 只冻结 relation 机制，不提前建立大规模 ontology，也不要求导航链接与关系记录双向镜像。模型推断只能形成 relation candidate，经既定治理后才能升级为结构化 Authority。
