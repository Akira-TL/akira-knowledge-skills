# 工作流角色映射

本文件把当前已安装 Matt 工程 Skill 使用的规范工作流角色映射到本仓 Issue Tracker 的具体值。GitHub 使用 label 字符串；下游 Skill 应读取这里的映射，不得假设规范角色名天然等于 Tracker 中的实际值。

| 工作流角色 | 本仓 GitHub label | 使用者 | 含义 |
| --- | --- | --- | --- |
| `ready-for-agent` | `ready-for-agent` | `to-tickets`、`triage` | 工作已充分定义，可由 Agent 执行 |
| `bug` | `bug` | `triage` | 请求属于缺陷 |
| `enhancement` | `enhancement` | `triage` | 请求属于功能或改进 |
| `needs-triage` | `needs-triage` | `triage` | 仍需维护者评估 |
| `needs-info` | `needs-info` | `triage` | 等待报告者补充信息 |
| `ready-for-human` | `ready-for-human` | `triage` | 需要人工实现或判断 |
| `wontfix` | `wontfix` | `triage` | 当前请求不会执行 |
| `wayfinder:map` | `wayfinder:map` | `wayfinder` | Wayfinder 的唯一 Map Issue |
| `wayfinder:research` | `wayfinder:research` | `wayfinder` | AFK Research 决策票 |
| `wayfinder:prototype` | `wayfinder:prototype` | `wayfinder` | 通过 Prototype 辅助决策的票 |
| `wayfinder:grilling` | `wayfinder:grilling` | `wayfinder` | 需要用户参与的 Grilling 决策票 |
| `wayfinder:task` | `wayfinder:task` | `wayfinder` | 为解除决策阻塞而执行的 Task |

Setup 只创建缺失 label；已经存在的 label 保留原有颜色和描述。以后改变工作流角色映射时，以本文件为兼容路径的唯一来源。
