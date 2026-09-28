# Changelog

## Unreleased

### Added

- 初始化 `Akira-TL/akira-knowledge-skills` 产品仓，并确立 `akira-knowledge` 作为 Primary Router。
- 实现 `0.1.x` 基础 Knowledge Loop：Existing Vault bootstrap / registration、显式 Capture、Curate proposal / approval、基础 Retrieval 与 revision-safe Maintenance。
- 增加 `knowledge-capture`、`knowledge-curate`、`knowledge-retrieve`、`knowledge-maintain` 四个领域 Skill，并共享同一 Markdown / SQLite Authority、identity、revision 与 round-trip safety 合同。
- 建立 canonical 临时 Obsidian Vault 黑盒测试接缝与 `docs/validation/0.1-release-gate.md` 发布就绪验收证据；当前尚未创建 GitHub tag / release。

### Changed

- 明确 Akira Knowledge 的运行时安装边界为项目级 / Vault 级 Skiloom `workspace` Target；`akira-knowledge` 及其领域依赖不进入用户级 `~/.agents/skills`，开发期继续使用显式 Git `main` source，直到正式 GitHub Release 完成。
