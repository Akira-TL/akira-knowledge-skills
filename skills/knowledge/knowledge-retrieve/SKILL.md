---
name: knowledge-retrieve
description: 只读检索已经进入 Akira Knowledge 管理范围的对象；0.2 在 stable identity、Authority 属性过滤与全文检索上统一使用显式检索范围，默认只检索当前知识资产，并始终回到 canonical Authority。
---

# Knowledge Retrieve

`knowledge-retrieve` 负责只读执行 Akira Knowledge 的基础 Retrieval Contract。它可以机械重建可重建检索 Projection，但不得因为检索结果自动修改正文、标签、普通链接、typed relation、权重或任何其他 Authority。

## 1. 检索范围

Exact、Authority property filter 与 Full-text 共用同一 scope 合同。未提供 `--scope` 时默认使用 `current`，只允许当前 Knowledge Asset 进入结果；Material Record 必须显式使用 `--scope material`。需要同时读取两类对象时重复参数：`--scope current --scope material`。

scope 只属于本次 retrieval request，不写回 Markdown、对象类别、生命周期状态、SQLite Authority 或 revision ledger。当前 `0.2.x` 只实现 `current` 与 `material` 两类 scope；对尚不存在的 `retired`、历史 revision 等范围必须受控失败，不得为了满足请求临时创造生命周期状态。

## 2. Exact retrieval

已知 Knowledge 对象 stable identity 时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-exact \
  --vault <vault> \
  --identity <stable-identity>
```

Exact 必须从当前已批准管理范围中的 Markdown 解析对象当前 locator，而不是把 SQLite 中可能陈旧的路径当作最终真相。用户在 Obsidian 中 rename / move 后，只要对象仍在管理范围内且保留同一 Knowledge identity，就应返回新的 canonical locator；检索本身不为了修正路径而写回 Authority 或 revision ledger。若 stable identity 对应对象不在本次 scope 内，则受控失败，而不是越过 scope 返回对象。

## 3. Authority property filter

按对象类别、材料记录状态或明确属于 Authority 的普通 top-level Property 过滤：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-filter \
  --vault <vault> \
  --kind knowledge_asset \
  --property topic=statistics

# 显式检索材料记录
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-filter \
  --vault <vault> \
  --scope material \
  --kind material_record \
  --status 待处理
```

材料记录状态使用 `--status 待处理` 或 `--status 已处理`，并显式进入 `material` scope。Akira Knowledge 保留字段必须使用专门参数，不通过通用 `--property` 重复解释；材料状态的 canonical 值来自结构化 Authority，Markdown 中的状态 Property 只是机器维护表示。

## 4. Full-text retrieval

搜索当前 Knowledge-managed Markdown；默认仍只返回 `current` scope 中的知识资产。检索材料正文时必须显式增加 `--scope material`：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-full-text \
  --vault <vault> \
  --query <text>
```

全文索引使用本地 SQLite FTS5 作为可重建 Projection。每次检索都以当前 Markdown Authority 的 fingerprint 判断索引是否过期；缺失或过期时可以机械重建。若 FTS Projection 损坏而 Authority 与结构化 registry 仍可读取，则必须显式降级为直接扫描当前 Authority，不能把损坏索引冒充成当前结果。

需要主动重建全文 Projection 时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-rebuild-index \
  --vault <vault>
```

重建只允许删除并重建检索 Projection，不得删除或重建 SQLite 中的结构化 Authority。

## 5. 任务相关知识集合

当用户希望“为当前任务取知识”时，当前 Agent 先把任务解释为显式检索计划，再调用共享执行入口：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-task \
  --vault <vault> \
  --task <current-task-description> \
  --scope current \
  --exact <optional-stable-identity> \
  --kind knowledge_asset \
  --property <key=value> \
  --query <optional-full-text-query>
```

`--exact` 与 `--query` 可以重复；Filter 路径由 `--kind`、`--status` 或 `--property` 中至少一项启用。确定性后端只执行已经显式给出的路径，不把任务描述本身当作隐藏搜索条件，也不自行从自然语言推断新的标签、关系或相关性 Authority。

任务相关结果按 `stable_identity` 去重；同一对象被多条路径命中时，保留每条真实 `matched_evidence`、`retrieval_reason` 与路径类型。返回的 `retrieval_plan`、任务描述与结果集合只存在于本次调用，不获得 Knowledge identity，不写入新的 Knowledge 对象，也不成为 Agent 当前任务 Context 或 Memory 的 Authority。

## 6. typed relation 只读扩展

任务相关检索可以把已经存在且已成为结构化 Authority 的 Relation Record 作为一条只读检索路径。当前 Agent 必须显式给出 relation seed、方向与可选 relation type：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-task \
  --vault <vault> \
  --task <current-task-description> \
  --relation-seed <stable-identity> \
  --relation-direction outgoing \
  --relation-type <optional-type>
```

方向只能是 `outgoing` 或 `incoming`。扩展只读取 SQLite 中已经存在的 Relation Record，并保留 relation identity、`source`、`type`、`target`、`provenance`、revision 与方向。普通 wikilink、backlink、共同 tag、全文共现或模型相似度都不能进入这条路径。

relation seed 与被扩展对象都受当前 Retrieval Scope 约束；默认 `current` 不能通过关系跳到 Material Record，只有显式增加 `material` scope 后才能返回材料对象。指向 Knowledge 外部引用或当前无法解析为 Knowledge 对象的端点不会被伪装成本地知识结果。

`0.2.x` 没有 relation create / accept / edit 用户命令；无 accepted Relation Record 时 relation path 正常返回空结果。relation candidate、关系治理与 ontology 扩展仍属于 `0.3.x`。

## 7. Obsidian Bases 动态视图

用户要在 Obsidian 中浏览当前知识与材料集合时，`knowledge-retrieve` 可以重建 Akira Knowledge 自有的 Bases Projection：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py views-rebuild \
  --vault <vault>
```

该命令生成一个官方 `.base` YAML 配置，其中至少包含 `Current Knowledge` 与 `Materials` 两个 table view，分别依据 `akira_knowledge_kind` 过滤当前 Knowledge Asset 与 Material Record；材料视图可以显示 `akira_knowledge_status`。这些字段仍由各自既有 Authority / Projection 合同拥有，`.base` 文件只保存筛选与展示配置。

视图目录带有 Akira ownership marker。只有已确认属于 Akira Knowledge 的 Projection 目录可以覆盖重建；同名但没有 marker 的用户目录必须 fail closed。用户删除或损坏已拥有的 `.base` 文件后可以重新生成，重建不得修改 Markdown、对象状态、relation、provenance 或 revision ledger。

当前没有 `retired` 等生命周期 Authority 时，不生成虚构 retired 视图。该 `.base` 文件是普通可重建本地配置，不需要 Obsidian 特有 link-aware mutation；后续若视图操作真正依赖 Obsidian 运行时语义，再按 Router 的官方 CLI / 上游 Skill 边界处理。

## 8. 结果合同

每条检索结果至少包含：

- `stable_identity`：稳定对象 identity；
- `object_kind`：材料记录或知识资产等对象类别；
- `canonical_locator`：当前 Markdown locator；
- `matched_evidence`：本次实际命中依据；
- `retrieval_reason`：为何召回该对象；
- `authority_text`：当前 canonical Markdown Authority，供调用方直接回读。

结果外层同时返回本次实际使用的 `scope`，让调用方可以检查对象为什么有资格进入本次检索。`0.2.x` 仍不提供统一 relevance score，也不把召回、排序或相似度解释成新的知识语义。

## 9. 完成与停止边界

检索完成时必须能够从结果回到当前 Authority，并明确说明命中依据。以下情况 fail closed：stable identity 在 registry 存在但当前管理范围中无法解析对应 Markdown、发现同一 stable identity 对应多个 Markdown、Markdown object kind 与结构化 registry 冲突、结构化 Authority store 本身不可读取。

当前已完成统一 Retrieval Scope、任务相关知识集合、accepted typed relation 的只读方向扩展与 Obsidian Bases 动态视图。完整 0.2 用户闭环与升级兼容门禁仍由后续票完成；向量检索、rerank 与 graph ranking 不属于 `0.2.x`。
