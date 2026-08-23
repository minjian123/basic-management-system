# GitLab 部署使用说明

> mjbk 代码托管 + CI 部署实录 · 2026-08-10

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › GitLab 部署使用说明　|　[← 上一个：MinIO](MinIO部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 GitLab CE（容器 `bms-gitlab`）承载 BMS 代码仓库、MR、CI 流水线与容器 Registry；
`bms-gitlab-runner` 以 Docker executor 执行 CI 任务（《[开发部署规划](../../规划/开发部署规划.md)》4.5）。

占位符取值：`<mjbk-IP>`、`<SSH账号>` 见《[本地资源](../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`（`MJBK_IP` / `MJBK_SSH_USER`）。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/gitlab.yml`（已同步至 mjbk `~/deploy/compose/gitlab.yml`）：

```yaml
gitlab:
  image: gitlab/gitlab-ce:latest
  container_name: bms-gitlab
  hostname: ${MJBK_IP:?请在 deploy/.env 设置 MJBK_IP}
  ports:
    - "8080:8080"    # HTTP（容器内 nginx listen_port=8080）
    - "5050:5050"    # Registry
    - "2222:22"      # SSH（系统 SSH 占 22）
  volumes:
    - /mnt/ssd2t/gitlab/config:/etc/gitlab
    - /mnt/ssd2t/gitlab/logs:/var/log/gitlab
    - /mnt/ssd2t/gitlab/data:/var/opt/gitlab   # ⚠️ 必须是 ssd2t！写错为 /mnt/data 会初始化空实例（见事故记录）
  shm_size: "256m"

renovate:                       # 依赖升级机器人（每日 cron 触发，一次性运行）
  image: renovate/renovate:latest
  container_name: bms-renovate
  depends_on:
    - gitlab
  environment:
    RENOVATE_PLATFORM: gitlab
    RENOVATE_ENDPOINT: http://gitlab:8080/api/v4
    RENOVATE_TOKEN: ${GITLAB_PAT}
    RENOVATE_REPOSITORIES: mj/bms     # 注意实际项目路径是 mj/bms 非 bms/bms
    LOG_LEVEL: info

gitlab-runner:
  image: gitlab/gitlab-runner:latest
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - runner-config:/etc/gitlab-runner
```

> **GitLab 数据放 NVMe SSD**（`/mnt/ssd2t/gitlab`，bind mount，规划 4.2）：
> 仓库读写频繁，放 NVMe 性能最佳；备份产物另存 HDD（`/mnt/data/backup/gitlab/`）实现异盘保护。

> **数据迁移记录**（2026-08-15）：GitLab 数据自 `/mnt/data/gitlab` 迁至 `/mnt/ssd2t/gitlab`
> ——停容器 → rsync 复制（原目录保留）→ 修改 `gitlab.yml` 挂载 → `docker compose up -d gitlab` 重建 → 验证 healthy；
> 验证通过后已删除原 `/mnt/data/gitlab`。

## 3. 部署步骤 <a id="deploy"></a>

```bash
# 1. 拉取镜像（DaoCloud 加速器支持 gitlab/gitlab-ce）
docker pull gitlab/gitlab-ce:latest

# 2. 启动（首次 reconfigure 初始化约 3-6 分钟；--env-file 注入 MJBK_IP/GITLAB_PAT）
cd ~/deploy
docker compose -f compose/gitlab.yml --env-file .env up -d gitlab

# 3. Renovate 手动触发（日常由 cron 每日 06:00 自动运行）
docker compose -f compose/gitlab.yml --env-file .env up -d renovate

# 3. 等待 HTTP 就绪（200/302）
curl -s -o /dev/null -w "%{http_code}" http://<mjbk-IP>:8080/users/sign_in
```

> 初始 root 密码：容器内 `/etc/gitlab/initial_root_password`（本次部署已记录至
> `~/deploy/.env` 的 `GITLAB_ROOT_PASSWORD`，首次登录后应修改）。

## 4. 验证 <a id="verify"></a>

```bash
curl -s http://<mjbk-IP>:8080/users/sign_in | grep "<title>"   # Sign in · GitLab
docker exec bms-gitlab gitlab-ctl status      # 全部 run 状态
```

本次部署结果：登录页正常（HTTP 200），gitaly / nginx / puma(8081) / postgresql / redis / sidekiq / sshd 全部运行。

## 5. 使用说明 <a id="use"></a>

| 项目 | 值 |
| --- | --- |
| 访问地址 | `http://<mjbk-IP>:8080` |
| 仓库克隆地址 | `http://<mjbk-IP>:8080/<group>/<repo>.git` 或 `ssh://git@<mjbk-IP>:2222/...` |
| Registry | `<mjbk-IP>:5050`（2026-08-22 随 02-4 main 流水线启用：gitlab.rb 配 `registry_external_url 'http://<mjbk-IP>:5050'` + `registry_nginx['listen_port']=5050` 后 `gitlab-ctl reconfigure`；mjbk daemon.json 加 `insecure-registries: ["<mjbk-IP>:5050"]`（HTTP 非 TLS，需重启 docker）；认证用 root PAT，`docker login <mjbk-IP>:5050 -u root --password-stdin`，推拉已实测） |
| 管理员账号 | `root`（密码见 `~/deploy/.env` 的 `GITLAB_ROOT_PASSWORD`） |

## 6. gitlab-runner 注册 <a id="runner"></a>

runner 容器已启动并注册（2026-08-10，runner `bacf4fd652a2`，concurrent=2）。注册步骤记录如下：

1. GitLab 界面获取认证 token：**管理区域 → CI/CD → Runners → 新建实例 runner**（勾选「允许未标记的作业」），得到 `glrt-...` token。
2. 注册（注意：新版 gitlab-runner 用认证 token 注册时**不能带 --tag-list / --run-untagged / --locked 等参数**，这些需在 GitLab 界面配置）：

    ```bash
    docker exec bms-gitlab-runner gitlab-runner register --non-interactive \
      --url http://<mjbk-IP>:8080 \
      --token <glrt-token> \
      --executor docker \
      --docker-image python:3.14-slim \
      --docker-volumes /var/run/docker.sock:/var/run/docker.sock
    ```

3. 并发上限（mjbk 6 核 12 线程，规划 4.5）：

    ```bash
    docker exec bms-gitlab-runner sed -i "s/concurrent = 1/concurrent = 2/" /etc/gitlab-runner/config.toml
    docker restart bms-gitlab-runner
    docker exec bms-gitlab-runner gitlab-runner verify
    ```

4. 验证：管理区域 Runners 页面显示 **在线**。

## 7. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-gitlab` |
| 查看日志 | `docker logs -f bms-gitlab` |
| 重启 | `docker restart bms-gitlab`（reconfigure 会重新执行） |
| 内部服务状态 | `docker exec bms-gitlab gitlab-ctl status` |
| 配置修改 | 编辑 `/mnt/ssd2t/gitlab/config/gitlab.rb`（root 权限）→ `docker restart bms-gitlab` |
| 流水线盯守 | AI 助手用 `gl_watch_pipeline` 插件工具；命令行 `python deploy/tools/gitlab/watch_pipeline.py --pipeline-id <ID>`（凭据读 deploy/.env 的 GITLAB_API_*，配合 bg 链路后台盯守，详见《通用后台执行器部署使用说明》） |
| 备份（每日 cron 2 点） | `docker exec bms-gitlab gitlab-backup create`，备份落 `/mnt/ssd2t/gitlab/data/backups/`，同步至 `/mnt/data/backup/gitlab/` |

## 8. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| reconfigure 报 Grafana 配置不支持 | `Reading unsupported config value grafana` | 新版 GitLab 移除内置 Grafana，删除 `grafana['enable']` 配置项 |
| puma 崩溃循环（端口冲突） | `EADDRINUSE bind 127.0.0.1:8080`，CPU 100% | GitLab 18 默认 puma 监听 TCP 8080；将 puma 端口改为独立端口 8081（`puma['listen']/['port']`） |
| GITLAB_OMNIBUS_CONFIG 不生效 | 容器重建后 gitlab.rb 仍是默认模板 | 该环境变量只在首次生成 gitlab.rb 时写入；后续修改直接编辑 `/mnt/ssd2t/gitlab/config/gitlab.rb`（bind mount 持久化） |
| 宿主机访问 8080 不通 | 容器内 200、宿主 000（曾 RST） | nginx `listen_port=8080` 后容器内监听 8080，docker 端口映射必须为 `8080:8080`（而非 8080:80） |
| 跳转链接缺少端口号 | 页面链接均为 `http://<mjbk-IP>/...`（无 :8080），登录/导航跳转后打不开 | `external_url` 必须带端口：`external_url 'http://<mjbk-IP>:8080'`，不再单独设置 `nginx['listen_port']`；配合 puma 独立端口 8081 避免端口冲突 |
| 外部访问容器端口全部不通 | Docker 发布端口对外不可达 | ufw 启用后需 `sudo ufw default allow routed`（FORWARD 链）并放行目标端口；本机访问用 `docker restart` 重建容器网络后验证 |
| CI job 一直 pending | job 排队不运行，API 查 runner 在线 | `.gitlab-ci.yml` 的 tags 与 runner 实际注册 tag 必须一致——本 runner 实际 tag 为 `bms`（界面配置，非 `bms,docker`）且未勾选「运行未标记的作业」；用 `GET /api/v4/runners/:id` 核对 `tag_list` |
| CI job 卡在 Pulling helper image | trace 停在 `Pulling docker image registry.gitlab.com/.../gitlab-runner-helper:...` 数十分钟 | registry.gitlab.com 国内访问慢，且 runner 19.x 对 helper 镜像默认 `pull_policy=[always]`（本地有镜像也强制联网校验）；处理：① 预拉缓存三镜像（python:3.14-slim、node:22-slim、gitlab-runner-helper 对应版本）；② config.toml `[runners.docker]` 加 `pull_policy = ["if-not-present"]` 后重启 runner |

## 9. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览
- 《[DockerEngine部署使用说明](DockerEngine部署使用说明.md)》：容器引擎与镜像加速
- 《[开发部署规划](../../规划/开发部署规划.md)》：4.5 GitLab 与 CI 基础设施
- 《[命名规范](../../规范/命名规范.md)》：镜像名 `bms-组件`、Registry 规划

> ⚠️ **事故记录（2026-08-22）**：`gitlab.yml` 变量化改造时挂载路径误写回迁移前的
> `/mnt/data/gitlab`，容器重建后 GitLab 在旧 HDD 路径初始化了**全新空实例**（项目数 0、
> 旧 PAT 全部失效）。恢复过程：改回 `/mnt/ssd2t/gitlab` 挂载 → `up -d gitlab` 重建 →
> 数据完整回归（6 项目含 mj/bms）→ rails console 重签 renovate-api token。
> **教训**：① 改 compose 必须核对 bind mount 路径与数据实际位置一致；② 空实例初始化
> 会覆盖挂载点内容（/mnt/data/gitlab 下已产生 588K 垃圾待清理）；③ PAT 失效优先排查
> 是否连到了错误实例，再考虑重签。Renovate 仓库路径为 `mj/bms`（非 bms/bms）。

> 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程 · 更新日期：2026-08-23（运维表补流水线盯守入口；此前更新：2026-08-15 数据迁至 /mnt/ssd2t/gitlab）