---
status: accepted
---

# 单 Vault 总知识库、根路由与工程工作区边界

Akira Knowledge 的默认产品形态是一个长期维护的总 Obsidian Vault，而不是按主题、知识类型或项目拆分多个独立 Knowledge 数据库。一个 Vault 只拥有一套根级 `.akira-knowledge/knowledge.sqlite` 结构化 Authority；Personal、Research、Development、具体项目、学科主题等均属于该 Vault 内的逻辑分类、目录、Properties、Relation 与动态视图维度。只有真实存在权限、ownership 或独立生命周期边界时，才另行讨论第二个 Vault，不以分类需要作为拆库理由。

Vault 根目录固定允许一个 `KNOWLEDGE.md` 作为人类与 Agent 共用的顶层路由。它只维护高层 Knowledge Map、主题 / 项目入口、工程工作区约定和长期导航，不复制每个 Knowledge Asset、SQLite registry、全文索引或 Relation Authority。Agent 进入该 Vault 后必须先读取根 `KNOWLEDGE.md`，再按其中的路由选择相关主题或项目区域；需要精确事实、跨目录召回、stable identity、revision 或 typed relation 时继续使用 Akira Knowledge Retrieval，而不是把递归目录扫描当成知识检索。根 `KNOWLEDGE.md` 自身是导航 Authority，不注册成普通 Knowledge Asset，也不由 Projection 自动覆盖。

初始化由 Primary Router `akira-knowledge` 的 bootstrap 职责拥有，不新增 `knowledge-init` Skill。显式 `init` 初始化一个独立 Git-backed Knowledge Vault：确保 Vault 根本身是 Git repository 顶层；创建缺失的 `收件箱/`、`项目/`、`知识/`、`记录/`、`成果/`、`归档/`、`系统/` 与 `.assets/` 默认内容区；创建缺失的根 `KNOWLEDGE.md`；在 `AGENTS.md` 中维护一个有 ownership marker 的 Akira Knowledge 指令块，要求 Agent 主动读取根路由；在 `.gitignore` 中维护可再生产物与工程噪声规则；并建立唯一的根级 `.akira-knowledge/` 配置与 SQLite store。初始化必须幂等，已有 `KNOWLEDGE.md` 与用户自己的 `AGENTS.md` / `.gitignore` 内容保持不变，只允许更新 Akira Knowledge 自有 marker block；如果 Vault 位于另一个 Git repository 内部则 fail closed，避免无意制造嵌套 repository。

Knowledge Vault 同时是可以进行真实工作的工程工作区。长期知识周围可以存在源代码、框架、实验实现、原型、展示站点、报告、可视化、脚本和其他可复用 artifact；这些内容不因为不是 Markdown 就被视为“库外垃圾”。新 Vault 的默认根路由使用直接可读的中文语义目录：`收件箱/`、`项目/`、`知识/`、`记录/`、`成果/`、`归档/`、`系统/` 与隐藏附件目录 `.assets/`。项目知识、源代码、框架和原型跟随 `项目/<project>/`；可跨任务复用的正式知识进入 `知识/`；按时间发生的事实进入 `记录/`；面向他人的完成品进入 `成果/`。这些目录是初始化默认入口，不是固定 taxonomy，用户可以通过根路由继续扩展自己的长期结构，但不使用 `00`–`99` 数字前缀作为必须记忆的分类语义。

依赖树、虚拟环境、缓存、测试缓存、构建目录和可再生产物不属于 Knowledge，也不得因为位于 Vault 内就进入盘点、registration 或 identity resolution。至少排除 `.git/`、`.obsidian/`、`.akira-knowledge/`、`node_modules/`、`.venv/`、`venv/`、`__pycache__/`、常见测试 / 类型 / lint cache、`.cache/`、`.next/`、`.nuxt/`、`dist/`、`build/`、`coverage/`、`htmlcov/`、`target/`，以及 Akira 自有的 `AK Views/` / `AK Graph/` Projection。Knowledge scan 必须在遍历阶段剪枝，而不是扫描后再忽略，以避免大型依赖目录造成性能与误注册风险。显式 registration 若指向这些排除区同样 fail closed。

Git 用于长期工作区版本管理、diff、backup 与 recovery，但不取代 Knowledge revision Authority。根 `.gitignore` 默认忽略 `AK Views/`、`AK Graph/`、依赖 / cache / build 目录和 SQLite WAL / SHM / journal；不得默认忽略 `.akira-knowledge/knowledge.sqlite` 本身，因为它包含不可由 Markdown 完整重建的结构化 Authority。持久化 source、code、prototype 与值得保留的成果应正常进入 Git；临时导出不得散落在 Vault 根目录或通过随意新增 `output/` 形成第二套无治理产物区。
