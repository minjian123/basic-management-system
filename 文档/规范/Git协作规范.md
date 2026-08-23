# Git 协作规范

> 分支模型 · 提交信息 · MR 流程 · 版本管理

[文档首页](../文档首页.md) › [规范](文档生成规范.md) › Git 协作规范　|　[下一个：数据库开发规范 →](数据库开发规范.md)

## 1. 目的与适用范围 <a id="purpose"></a>

统一 BMS 项目的 Git 协作方式：分支组织、提交信息、MR 评审与版本管理，保证多人协作时历史清晰、可追溯。
适用于本仓库全部开发与文档变更；与《[命名规范](命名规范.md)》第 5 节 Git 命名配套。
`<mjbk-IP>` 取值见《[本地资源](../用户文档/本地资源.md)》。

> **⚠️ 当前阶段简化执行（2026-08-23）**：单人开发且尚无基本产品，本规范第 6 节 MR 流程（feature 分支 → MR → 流水线门禁 → Squash 合入）**整体暂缓**——日常改动经两级指令直接提交并直推 main（含代码改动由 main 流水线自动冒烟验证）。本文其余章节（提交信息、版本管理）照常执行。**恢复条件**：产品成型或团队扩为多人协作时，恢复完整 MR 门禁（含核心模块 AI 交叉评审），届时删除本说明框即可，正文无需改动。决策记录见《[开发部署规划](../规划/开发部署规划.md)》第 7 节。

## 2. 仓库与远端 <a id="repo"></a>

| 远端 | 地址 | 角色 |
| --- | --- | --- |
| `gitlab`（主） | `http://<mjbk-IP>:8080/bms/bms.git` | 开发、MR、CI、Registry（唯一远端，日常推送目标） |

> 本地仅配置 `gitlab` 一个远端；GitHub 只读归档由 GitLab 端 push mirror 自动同步，本地不配置 GitHub remote，避免误推。

## 3. 分支模型 <a id="branch"></a>

| 分支 | 命名 | 说明 |
| --- | --- | --- |
| main | `main` | 保护分支（仅 Maintainers 推送/合并），始终可部署 |
| 功能分支 | `feature/描述` | 新功能：`feature/workflow-engine` |
| 缺陷修复 | `fix/描述` | 缺陷修复：`fix/login-500` |
| 文档 | `docs/描述` | 文档与规范变更：`docs/deploy-guide` |
| 重构 | `refactor/描述` | 结构调整：`refactor/permission-engine` |
| 维护 | `chore/描述` | 构建、依赖、杂项：`chore/renovate-deps` |
| 发布 | `release/版本` | 发布前准备（可选）：`release/v1.2.0` |

- 分支名小写、kebab-case、以「类型/」前缀，描述用英文或语义缩写，不夹带版本号以外的数字编号。
- 功能分支从最新 main 切出：`git checkout -b feature/xxx gitlab/main`。
- 禁止直接向 main 推送（保护分支），一切变更经 MR 合入。

## 4. 提交信息 <a id="commit"></a>

格式：`type(scope): 中文描述`，一行主题 + 必要时空行 + 正文说明：

```
feat(wf): 新增采购申请三级审批流程
docs(资料): 补充 GitLab 迁移说明
fix(auth): 修复刷新令牌并发过期竞态
chore(deps): 升级 fastapi 至 0.115

- 变更点 1（为什么改）
- 变更点 2
```

| type | 用途 | 示例 |
| --- | --- | --- |
| feat | 新功能 | `feat(user): 用户导入支持租户批量` |
| fix | 缺陷修复 | `fix(wf): 驳回后待办未清除` |
| docs | 文档变更 | `docs: 更新部署说明` |
| refactor | 重构（无行为变化） | `refactor(rbac): 权限计算提取独立引擎` |
| test | 测试 | `test(api): 补充越权用例` |
| perf | 性能优化 | `perf(query): 列表查询减少 N+1` |
| style | 格式（不影响逻辑） | `style: 统一引号风格` |
| chore | 构建/依赖/杂项 | `chore(deps): renovate 批量升级` |

- scope 为模块名（user、wf、rbac、dept、open、docs、deps 等），无明确模块可省略。
- 一个提交只做一件事；禁止「顺便改」混入无关改动。
- 提交信息用中文描述（与《[命名规范](命名规范.md)》第 2 节语言分工一致）。

## 5. MR 流程 <a id="mr"></a>

1. **推送**：功能分支 push 至 gitlab：`git push gitlab feature/xxx`。
2. **创建 MR**：目标分支 main，标题遵循提交信息格式（`feat(wf): ...`），描述注明需求来源与验收点。
3. **CI 检查**：MR 流水线须全绿（ruff、pytest、ESLint、Vitest、双端构建）方可合并。
4. **评审**：至少 1 人评审通过（见《[代码评审规范](代码评审规范.md)》），评审意见逐条处理。
5. **合入**：Squash 合并（保持 main 历史线性），删除源分支。

> main 分支合入后 GitLab 自动 push mirror 同步 GitHub 归档。

## 6. 版本管理 <a id="version"></a>

- 里程碑用语义化版本标签：`v1.0.0`（主版本.次版本.修订），仅打在 main 上。
- 标签打于发布提交：`git tag -a v1.2.0 -m "v1.2.0"`，推送 `git push gitlab v1.2.0`。
- 镜像版本与标签一致（`bms-backend:v1.2.0`，见《[部署发布规范](部署发布规范.md)》）。

## 7. 同步与归档 <a id="sync"></a>

- 本地同步：`git fetch gitlab` 拉取最新，`git pull gitlab main` 更新本地 main。
- GitHub 归档由 GitLab push mirror 自动完成；镜像异常时参照《[GitLab迁移使用说明](../资料/工具/GitLab迁移使用说明.md)》第 6 节处理。
- 不保留本地陈旧分支；合入并删除源分支后本地同步删除：`git branch -d feature/xxx`。

## 8. 检查清单 <a id="checklist"></a>

- □ 分支名符合「类型/描述」，从最新 main 切出
- □ 提交信息 `type(scope): 中文描述`，单提交单职责
- □ MR 标题与描述规范，CI 全绿，评审通过后 Squash 合并
- □ 不直推 main；本地仅配置 gitlab 远端，GitHub 归档走 push mirror 自动同步
- □ 发布标签语义化 `vX.Y.Z`，与镜像版本一致

> 依《文档生成规范》编写 · 与《命名规范》《代码评审规范》配套 · 生成日期：2026-08-11
