# GitLab 迁移使用说明

> BMS 仓库迁移至 GitLab · GitHub 归档同步实录 · 2026-08-11

[文档首页](../../文档首页.md) › [资料](../开发服务器/开发服务器部署使用说明总览.md) › GitLab 迁移使用说明　|　[同级：GitLab 部署使用说明 →](../开发服务器/GitLab部署使用说明.md)

## 1. 目的与现状 <a id="purpose"></a>

按《[开发部署规划](../../规划/开发部署规划.md)》第 4.5、7 节，BMS 代码仓库以**自托管 GitLab 为主仓库**
（MR 评审 + CI），**GitHub 作只读归档同步**（push mirror 单向）。
`<mjbk-IP>` 取值见《[本地资源](../../用户文档/本地资源.md)》。

| 仓库 | 地址 | 角色 |
| --- | --- | --- |
| GitLab（主） | `http://<mjbk-IP>:8080/bms/bms.git` | 代码托管、MR、CI、Registry |
| GitHub（归档） | `https://github.com/minjian123/basic-management-system.git` | push mirror 单向同步，只读 |

## 2. 迁移步骤 <a id="migrate"></a>

### 2.1 前置条件 <a id="prepare"></a>

- GitLab CE 已部署并可用（见《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》）。
- GitHub 目标仓库已存在（`minjian123/basic-management-system`）。
- GitLab 管理员 PAT（api + write_repository 权限）：用 rails runner 生成：

```bash
docker exec bms-gitlab gitlab-rails runner "
u = User.find_by_username('root')
tok = u.personal_access_tokens.create!(name: 'migration-api', scopes: [:api, :write_repository], expires_at: 1.year.from_now)
puts tok.token"
```

### 2.2 创建组与项目 <a id="create"></a>

使用 GitLab REST API（HTTP 头 `PRIVATE-TOKEN: <PAT>`）：

```bash
# 创建组 bms
POST /api/v4/groups                {"name": "bms", "path": "bms"}
# 创建项目 bms/bms（private，默认分支 main）
POST /api/v4/projects             {"name": "bms", "path": "bms", "namespace_id": <组id>,
                                   "visibility": "private", "default_branch": "main"}
```

> 本次部署：组 id=37，项目 id=2，路径 `bms/bms`（与规划 5.2 克隆示例一致）。

### 2.3 本地推送 <a id="push"></a>

```bash
git remote add gitlab http://root:<PAT>@<mjbk-IP>:8080/bms/bms.git
git push gitlab --all      # 全部历史分支
git push gitlab --tags
```

> 本地 remote 现状：`origin`（GitHub，原主）已删除，仅保留 `gitlab` = GitLab（现主）。GitHub 归档由 GitLab 端 push mirror 自动完成，本地不配置 GitHub remote 避免误推。

### 2.4 GitHub push mirror <a id="mirror"></a>

在 GitLab 项目设置中配置 push mirror（或 API）：

```bash
POST /api/v4/projects/2/remote_mirrors
{"url": "https://minjian123:<GitHub PAT>@github.com/minjian123/basic-management-system.git",
 "enabled": true}
```

> push mirror 需要 GitHub PAT（repo 权限）；GitLab 推送 main 后自动同步至 GitHub。
> 若 API 手动触发同步端点 404（GitLab 18），可用 rails runner 触发：
>
> ```bash
> docker exec bms-gitlab gitlab-rails runner "Project.find(2).remote_mirrors.first.sync"
> ```

### 2.5 main 保护分支 <a id="protect"></a>

GitLab 新项目默认保护 main（推送/合并仅 Maintainers），与规划第 7 节一致——开发者 push feature 分支、经 MR 合入。确认命令：

```bash
GET /api/v4/projects/2/protected_branches   # main: push=Maintainers merge=Maintainers
```

## 3. 验证结果 <a id="verify"></a>

| 项目 | 结果 |
| --- | --- |
| GitLab 仓库内容 | 7 项（.opencode / deploy / 文档 / .gitignore / AGENTS.md / LICENSE / README.md） |
| GitHub 同步 | 最新提交 `1d4681a` 已镜像（GitHub API 确认） |
| main 保护 | push=Maintainers、merge=Maintainers |
| 本地 remote | gitlab=GitLab（唯一远端），origin（GitHub）已删除 |

## 4. 日常使用流程 <a id="workflow"></a>

1. 开发：`git checkout -b feature/xxx` 分支开发。
2. 推送：`git push gitlab feature/xxx` → GitLab 提 Merge Request（CI 通过方可合并）。
3. 合入：MR 合入 main（maintainers）后，GitLab 自动 push mirror 同步至 GitHub 归档。
4. 同步验证：GitHub 网页查看 main 是否已更新（本地无 origin 远端，不 fetch GitHub）。

> GitHub 为只读归档，镜像由 GitLab 端 push mirror 自动完成；本地不配置 GitHub remote，禁止直接向 GitHub 推送代码（避免与 mirror 冲突）。

## 5. 凭据管理 <a id="creds"></a>

- GitLab PAT（migration-api）：root 名下，有效期 1 年，存 mjbk `~/deploy/.env`（`GITLAB_PAT`）。
- 本地 remote URL 内嵌 PAT：仅本机可见；如需更换 token 用 `git remote set-url gitlab <新地址>`。
- GitHub PAT：用户本人持有，凭据同时配置在 GitLab push mirror 中。
- 凭据汇总见《[本地资源](../../用户文档/本地资源.md)》（已 gitignore，不入库）。

## 6. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| mirror 手动同步 API 404 | `POST /projects/2/remote_mirrors/1/update` 返回 404 | GitLab 18 该端点不可用；改用 rails runner `remote_mirrors.first.sync` 触发；日常同步由 GitLab 自动执行 |
| 保护分支配置 409 | `POST protected_branches` 返回 409 Conflict | 新项目默认已保护 main（Maintainers），无需重复创建，GET 确认即可 |

## 7. 关联文档 <a id="related"></a>

- 《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》：GitLab 部署与 runner 注册
- 《[开发部署规划](../../规划/开发部署规划.md)》：4.5 GitLab 与 CI、第 7 节开发工作流
- 《[本地资源](../../用户文档/本地资源.md)》：凭据汇总
- 《[文档首页](../../文档首页.md)》：全量文档索引

> 依《文档生成规范》编写 · 记录 2026-08-11 实际迁移过程 · 更新日期：2026-08-11