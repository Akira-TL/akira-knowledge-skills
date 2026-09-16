---
name: knowledge-retrieve
description: 只读检索已经进入 Akira Knowledge 管理范围的材料记录与知识资产；0.1 支持 stable identity 精确读取、Authority 属性过滤与当前 Markdown 全文检索，并始终回到 canonical Authority。
---

# Knowledge Retrieve

`knowledge-retrieve` 负责只读执行 Akira Knowledge 的基础 Retrieval Contract。它可以机械重建可重建检索 Projection，但不得因为检索结果自动修改正文、标签、普通链接、typed relation、权重或任何其他 Authority。

## 1. Exact retrieval

已知 Knowledge 对象 stable identity 时执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-exact \
  --vault <vault> \
  --identity <stable-identity>
```

Exact 必须从当前已批准管理范围中的 Markdown 解析对象当前 locator，而不是把 SQLite 中可能陈旧的路径当作最终真相。用户在 Obsidian 中 rename / move 后，只要对象仍在管理范围内且保留同一 Knowledge identity，就应返回新的 canonical locator；检索本身不为了修正路径而写回 Authority 或 revision ledger。

## 2. Authority property filter

按对象类别、材料记录状态或明确属于 Authority 的普通 top-level Property 过滤：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py retrieve-filter \
  --vault <vault> \
  --kind knowledge_asset \
  --property topic=statistics
```

材料记录状态使用 `--status 待处理` 或 `--status 已处理`。Akira Knowledge 保留字段必须使用专门参数，不通过通用 `--property` 重复解释；材料状态的 canonical 值来自结构化 Authority，Markdown 中的状态 Property 只是机器维护表示。

## 3. Full-text retrieval

搜索当前 Knowledge-managed Markdown：

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

## 4. 结果合同

每条检索结果至少包含：

- `stable_identity`：稳定对象 identity；
- `object_kind`：材料记录或知识资产等对象类别；
- `canonical_locator`：当前 Markdown locator；
- `matched_evidence`：本次实际命中依据；
- `retrieval_reason`：为何召回该对象；
- `authority_text`：当前 canonical Markdown Authority，供调用方直接回读。

`0.1.x` 不提供统一 relevance score，也不把召回、排序或相似度解释成新的知识语义。

## 5. 完成与停止边界

检索完成时必须能够从结果回到当前 Authority，并明确说明命中依据。以下情况 fail closed：stable identity 在 registry 存在但当前管理范围中无法解析对应 Markdown、发现同一 stable identity 对应多个 Markdown、Markdown object kind 与结构化 registry 冲突、结构化 Authority store 本身不可读取。

当前版本不承担 typed relation traversal、任务相关知识集合、Bases 动态视图、向量检索、rerank 或 graph ranking；这些按 0.x 路线图进入后续版本。
