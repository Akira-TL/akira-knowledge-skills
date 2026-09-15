# Issue Tracker：GitHub

本仓的 Issue、Spec、Wayfinder Map 与决策票统一保存在 GitHub Issues 中。所有操作使用 `gh` CLI；仓库身份从当前 Git remote 推断。

## 基本操作

- 创建 Issue：`gh issue create --title "..." --body "..."`；多行正文使用 heredoc。
- 读取 Issue：`gh issue view <number> --comments`。
- 列出 Issue：按实际工作流使用 `gh issue list` 并读取 `number`、`title`、`body`、`labels`、`comments`。
- 评论：`gh issue comment <number> --body "..."`。
- 添加 / 删除 label：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`。
- 列出 label：优先使用 `gh label list`；旧版 CLI 遇到兼容问题时允许用 `gh api` 直接读取 GitHub REST API。
- 创建缺失 label：`gh label create "<name>"` 或等价 `gh api`；setup 不使用 `--force` 覆盖已存在 label。
- 关闭：`gh issue close <number> --comment "..."`。

工作流角色与实际 label 的映射见 `docs/agents/triage-labels.md`。

## Pull Request 是否作为 triage 请求入口

**否。** 本仓当前只把 GitHub Issues 作为请求和规划入口；Pull Request 不自动进入 `triage` 工作流。

GitHub 的 Issue 与 Pull Request 共用编号空间。遇到来源不明的裸编号时，应先确认对象类型，不因编号相同混淆二者。

## Tracker 发布与读取

当 Skill 要求“发布到 issue tracker”时，创建 GitHub Issue。

当 Skill 要求“读取相关 ticket”时，通过 `gh issue view <number> --comments` 获取当前正文、评论与 labels。

## 工作项关系

需要协调多个 Issue 的 Skill 使用 GitHub 原生关系作为 canonical 表示。

在使用 sub-issue、blocked-by 等 CLI convenience flag 前，实际检查当前安装的 `gh` 是否支持；不得仅凭版本号或在线文档假定本机能力。若当前 CLI 缺少 convenience flag，但 GitHub API 支持对应关系，则直接通过已认证的 `gh api` 操作 GitHub 原生关系，不要求为了完成当前任务先升级 CLI。

### Blocking

GitHub 原生 issue dependency 是 canonical、UI 可见的阻塞关系。

若当前 `gh` 支持 `--blocked-by` / `--add-blocked-by` 与 `blockedBy` 字段，优先直接使用。否则：

1. 用 `gh api 'repos/{owner}/{repo}/issues/<blocker>' --jq .id` 取得 blocker 的数据库 ID；
2. 用 `gh api --method POST 'repos/{owner}/{repo}/issues/<child>/dependencies/blocked_by' -F issue_id=<blocker-id>` 建立关系；
3. 用 `gh api --paginate 'repos/{owner}/{repo}/issues/<child>/dependencies/blocked_by'` 读取 blocker。

只有 GitHub dependency API 本身不可用时，才退化为 ticket body 中机器可读的 `Blocked by: #<n>, #<n>`。

### Frontier

列出当前工作流相关的开放 Issue，并用当前最强可用方式读取 blockers。存在未解决 blocker 或已被工作流正式 claim 的项目不属于 frontier；其余项目按 owning workflow 的排序规则处理。

### Claim

当不同 Worker 拥有不同 GitHub identity 时，`gh issue edit <n> --add-assignee @me` 可以作为 tracker-visible claim。

若多个 Agent 共用同一个 GitHub identity，assignee 只表示可见状态，不提供互斥保证；必须遵守 owning coordination workflow 的 deterministic claim 协议，或保持串行处理。

## 普通实现票完成

实现票只有在全部既定 Acceptance Criteria 都已由最终提交、验证和 review evidence 满足后才能关闭。只勾选已真实满足的 criterion，留下简洁证据评论，并移除 `ready-for-agent`。存在未满足 criterion 时保持 Issue 开放，不因某个子票完成而顺带关闭父 Spec / parent Issue。

## Wayfinding 操作

`wayfinder` 使用一个 Map Issue 和其 child Issues 组成决策地图。Map 与 ticket 的 workflow role 均使用 `docs/agents/triage-labels.md` 中的配置。

### Map

Map 是唯一携带 `wayfinder:map` label 的 Issue，保存 Destination、Notes、Decisions so far、Not yet specified 与 Out of scope。

创建时使用：

```bash
gh issue create --label "wayfinder:map" ...
```

### Child ticket

Wayfinder ticket 必须作为 Map 的 child issue，并按类型使用：

- `wayfinder:research`
- `wayfinder:prototype`
- `wayfinder:grilling`
- `wayfinder:task`

若当前 CLI 原生支持 parent/sub-issue flags，直接使用；否则先正常创建 child，再：

```bash
gh api 'repos/{owner}/{repo}/issues/<child>' --jq .id
gh api --method POST 'repos/{owner}/{repo}/issues/<map>/sub_issues' -F sub_issue_id=<child-id>
```

只有 GitHub sub-issue API 本身不可用时，才退化为 Map task list + child body 中的 `Part of #<map>` 约定。

### Resolve

Wayfinder ticket 解决后依次执行：

1. `gh issue comment <n> --body "<answer>"` 写入 resolution；
2. `gh issue close <n>`；
3. 在 Map 的 Decisions so far 中追加该 ticket 的**名称、链接与一句结论**。

用户可读叙述始终以 ticket 名称为主，不用裸 Issue 编号代替名称。
