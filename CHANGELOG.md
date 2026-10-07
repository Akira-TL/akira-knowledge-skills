# Changelog

## Unreleased

### Added

- 增加 Human-readable Knowledge Writing Contract 与确定性 `writing-check`：Curate 新建正文必须清零结构 / 风格 finding，更新正文以当前 Authority 为 baseline，只阻止新增或加重写作问题；合同覆盖检索型标题、段落与句子密度、标题层级、列表 / 表格、wikilink、verification 与反 AI 元话语，并明确 Capture 保留原始输入不执行润色。
- 增加单 Vault Knowledge workspace 初始化入口：建立根 `KNOWLEDGE.md` 人类 / Agent 路由、`AGENTS.md` 主动读取指针、独立 Git repository、最低公共 `收件箱/` / `系统/` / `.assets/` 入口，以及根级 `.akira-knowledge/knowledge.sqlite` 唯一结构化 Authority；一级内容 taxonomy 改由 `KNOWLEDGE.md` 按真实领域定义，不再强制“项目 / 知识 / 记录 / 成果”或 `00`–`99` 数字前缀。
- 初始化 `Akira-TL/akira-knowledge-skills` 产品仓，并确立 `akira-knowledge` 作为 Primary Router。
- 实现 `0.1.x` 基础 Knowledge Loop：Existing Vault bootstrap / registration、显式 Capture、Curate proposal / approval、基础 Retrieval 与 revision-safe Maintenance。
- 增加 `knowledge-capture`、`knowledge-curate`、`knowledge-retrieve`、`knowledge-maintain` 四个领域 Skill，并共享同一 Markdown / SQLite Authority、identity、revision 与 round-trip safety 合同。
- 建立 canonical 临时 Obsidian Vault 黑盒测试接缝与 `docs/validation/0.1-release-gate.md` 发布就绪验收证据；当前尚未创建 GitHub tag / release。

### Fixed

- `writing-check` 现在识别 `a.` / `b)` 等字母有序列表项，避免教学判断题和练习清单被错误拼接成一个长 prose 段落。
- `writing-check` 的句长与段落长度统计现在只计算 Markdown link 的可见链接文本，不把隐藏的 URL destination 计入 prose 长度，避免官方文档长链接造成 `long_sentence` / `long_paragraph` 假阳性。
- `writing-check` 现在把块级 LaTeX `\\[...\\]` 与 `$$...$$` 视为非正文块并保留原行号占位，避免统计 / 科研知识中的长公式被误判为 `long_sentence` 或墙状段落。

### Changed

- Knowledge 扫描与 identity resolution 在遍历阶段排除 `.git/`、`.obsidian/`、`.akira-knowledge/`、`node_modules/`、`.venv/`、cache / build 目录以及 `AK Views/` / `AK Graph/` Projection；这些路径也不能显式 registration，避免工程依赖和生成物污染总知识库。
- 明确 Akira Knowledge 的运行时安装边界为项目级 / Vault 级 Skiloom `workspace` Target；`akira-knowledge` 及其领域依赖不进入用户级 `~/.agents/skills`，开发期继续使用显式 Git `main` source，直到正式 GitHub Release 完成。
