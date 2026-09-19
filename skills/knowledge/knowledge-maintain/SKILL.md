---
name: knowledge-maintain
description: 执行 revision-safe 的显式知识更新、确定性状态同步、Relation Record 显式撤回，以及 0.4.x 已实现的 Knowledge Asset 明确退役；在写入前阻止陈旧 revision 覆盖较新的 Authority。
---

# Knowledge Maintain

`knowledge-maintain` 负责显式用户触发的 revision-safe 更新和确定性状态同步；`0.3.x` 由本 Skill 执行已接受 Relation Record 的显式撤回，`0.4.x` 已增加 Knowledge Asset 的明确退役闭环。系统性回顾、自动发现陈旧/冲突关系、Source 更新监控、supersede、批量维护与知识网络健康检查仍未实现，不得提前描述为现有能力。

## 1. 同步当前对象状态

用户直接在 Obsidian 中移动、重命名或编辑已注册 Markdown 后，进入维护或写入准备时先同步对象：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-sync \
  --vault <vault> \
  --identity <stable-identity>
```

同步按 stable identity 在当前已批准 Knowledge 管理范围中重新解析 Markdown。若 current locator 改变，则登记 `external_move` revision；若人类内容 Authority fingerprint 改变，则登记 `external_edit` revision；两者同时发生时登记 `external_move_and_edit`。stable identity 始终不因这些变化改变。

Authority fingerprint 只用于已注册 Markdown 的外部内容变更检测，不是对象 identity，也不构成“对 Vault 所有文件做内容哈希”的要求。Knowledge-owned metadata 不作为人类正文 fingerprint 的语义内容。

材料记录的状态由结构化 Authority 拥有；如果用户手工修改了 Markdown 中的 `akira_knowledge_status` 镜像而与结构化状态不一致，维护流程必须把它视为 drift 并 fail closed，而不是把该镜像静默接管为 Authority。

## 2. 既有知识更新提案

既有知识的正文语义更新仍由 `knowledge-curate` 形成 proposal。形成候选正文前先执行 `maintain-sync`，记录返回的 current revision，再读取当前 Authority；`knowledge-curate` 保存 update proposal 时必须携带这个实际读取的 `base_revision`。proposal 保存阶段会再次同步目标，如果期间 revision 已变化则立即停止，防止把基于旧正文生成的 proposal 错绑到新状态。依据材料也在 proposal 保存前同步并记录 basis revision。

用户未明确批准时，不调用任何应用命令，Knowledge Authority 保持不变。

用户明确批准 update proposal 后，由本 Skill 执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-apply-update \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

执行前再次同步目标与材料。若 proposal 的 `base_revision` 之后出现 `external_edit`、`external_move_and_edit` 或其他不能机械证明与正文更新互不相交的 Authority 变化，则 fail closed，保留当前较新的 Authority，并要求从当前 revision 重新形成 proposal。

纯 `external_move` 只改变 locator，可以机械证明与已批准的正文替换互不相交，因此允许在新的 canonical locator 上继续执行。当前版本不做猜测式语义三方合并。

## 3. 应用更新

通过 revision 门禁后，只替换知识资产的人类正文 body，保留现有 YAML frontmatter、用户 Properties 与 Akira Knowledge identity / kind。成功写入后：

- 同一 stable identity 保持不变；
- current locator 使用同步后的实际路径；
- Authority revision 单调推进；
- revision history 记录 `updated_from_proposal`；
- proposal 记录为 applied，并关联原 target identity；
- proposal 的材料 provenance 写入结构化 Authority；
- 仍为 `待处理` 的依据材料可以确定性进入 `已处理`，材料本身不删除。

Projection / 全文索引重建不得推进 Authority revision；这一职责继续由 `knowledge-retrieve` 的可重建 Projection 机制承担。

## 4. Knowledge Asset 明确退役

用户明确决定某个当前 Knowledge Asset 不再进入默认当前知识范围时，先基于实际读取的 current revision 形成退役提案：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-propose-retire \
  --vault <vault> \
  --identity <knowledge-asset-id> \
  --base-revision <actually-read-revision> \
  --reason <retire-reason>
```

提案只保存待治理的 lifecycle 变化，不立即修改 Authority。用户明确批准后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py maintain-apply-retire \
  --vault <vault> \
  --proposal-id <proposal-id> \
  --confirmed-approval
```

批准执行前重新同步目标；若目标 revision 已不同，提案 fail closed 并保持 pending。成功退役后：

- stable identity、canonical Markdown、history 与既有 provenance 保留；
- Knowledge Asset revision 单调推进；
- structured lifecycle Authority 进入 `retired`；
- Markdown 中的 `akira_knowledge_lifecycle: retired` 只是 Knowledge-owned 机器维护表示，不成为第二 Authority；
- 默认 `current` Retrieval Scope 排除该对象；
- 显式 `retired` scope 仍可通过 Exact / Filter / task retrieval 回读同一 identity；
- Material Record 的 `待处理 / 已处理` 状态不受影响。

退役不等于 supersede；替代关系与更完整的长期 Review 仍由后续 0.4 实现票完成。

## 5. Relation Record 显式撤回

用户明确要求撤回一个当前正式关系时，调用方必须先读取该 Relation Record 的当前 revision，并在确认后执行：

```bash
uv run python <akira-knowledge-skill-root>/scripts/knowledge.py relation-revoke \
  --vault <vault> \
  --relation-id <relation-id> \
  --expected-revision <actually-read-revision> \
  --confirmed-revoke
```

撤回只允许在调用方实际读取的 expected revision 仍等于当前 relation revision 时执行；如果其间 relation 因 provenance 增补或其他 Authority 变化推进了 revision，则 fail closed，要求重新读取并再次确认。

成功撤回：

- 保留 relation stable identity；
- 保留 source / type / target；
- 保留全部 provenance 与 revision history；
- relation status 进入 `revoked`；
- relation revision 单调推进；
- 默认 typed relation traversal 不再消费该关系；
- 不物理删除 Relation Record。

对已经 revoked 的关系，如果调用方提供的 expected revision 正好等于当前 revision，则作为幂等操作返回，不再次推进 revision；若使用旧 revision 重复操作，仍按 stale-write 规则 fail closed。

撤回是用户主动纠错能力，不等于系统自动判断关系已经陈旧或冲突。自动 stale / conflict 发现、Source 更新影响检查、批量 Review 与自动生成撤回候选继续属于 `0.4.x`。

## 6. 停止边界

以下情况必须停止而不是覆盖或猜测：

- stable identity 在当前管理范围内找不到唯一 Markdown；
- object kind 与结构化 registry 不一致；
- proposal 不是 pending update proposal；
- 没有明确用户批准；
- proposal target 或依据材料在 basis revision 后发生相关 Authority 编辑；
- Knowledge-owned 状态镜像与结构化 Authority 漂移；
- 结构化 Authority store 不可读取。

`0.1.x` 不引入多 Agent 锁、claim、并发仲裁或自动语义 merge；这些也不属于 Akira Knowledge 当前产品职责。
