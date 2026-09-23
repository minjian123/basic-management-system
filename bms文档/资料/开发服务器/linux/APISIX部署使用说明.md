# APISIX 部署使用说明

> mjbk 边缘网关（Apache APISIX standalone）部署实录 · 2026-09-23

[文档首页](../../../文档首页.md) › [资料](../../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md) › APISIX 部署使用说明　|　[← 上一个：防火墙](防火墙部署使用说明.md)　|　[下一个：nginx →](nginx部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 Apache APISIX（容器 `bms-apisix`）是本项目**边缘统一入口**：外部流量经它按服务目录路由到各后端服务，承担路由、边缘认证、限流、灰度与边缘观测（认证 / 限流能力随 04_02 / 04_03 接入）。
本说明记录其**standalone（文件驱动）**部署形态、声明式配置来源、部署与运维步骤、排障经验。
`<mjbk-IP>` / `<SSH账号>` 取值见《[本地资源](../../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`。

配置语义、外部路径约定与 K8s 平移口径见**平台**《架构设计 · API 网关与边缘》「部署形态与演进」节与实现侧详细设计（平台项目 `02_后端基座与服务化地基/任务/04_API网关与边缘/`）。编排随仓库 `deploy/` 版本管理。

## 2. 部署形态 <a id="shape"></a>

- **模式**：APISIX **standalone 文件驱动**——`deployment.role: data_plane` + `role_data_plane.config_provider: yaml`；**不引入 etcd / Admin API / Dashboard**。
- **配置**：路由 / 上游落 `deploy/gateway/apisix.yaml`（**由服务目录生成**，禁止手改），APISIX 每 1 秒轮询该文件并**热更新内存**（不重启进程）。
- **容器与镜像**：容器 `bms-apisix`，镜像 `apache/apisix:3.18.0-debian`（锁定版本），经官方 `APISIX_STAND_ALONE=true` 开关跳过 etcd 初始化。
- **上游寻址**：按服务目录登记的服务标识经 Compose DNS 寻址（`{service_key}:8000`），不硬编码 IP。
- **与 nginx 分工**：静态资源由 [nginx](nginx部署使用说明.md) 托管，`/api/` 流量反代至本网关，网关**只处理 API**。

## 3. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/gateway.yml`（已同步至 mjbk `~/deploy/compose/gateway.yml`）：

```yaml
apisix:
  image: apache/apisix:3.18.0-debian
  container_name: bms-apisix
  restart: unless-stopped
  environment:
    TZ: Asia/Shanghai
    APISIX_STAND_ALONE: "true"
  # 目录挂载 + 启动软链（单文件 bind 在文件被替换后容器内仍指向旧 inode，无法热加载）
  entrypoint: ["/bin/sh", "-c"]
  command:
    - |
      set -e
      ln -sfn /etc/bms-gateway/config.yaml /usr/local/apisix/conf/config.yaml
      ln -sfn /etc/bms-gateway/apisix.yaml /usr/local/apisix/conf/apisix.yaml
      exec /docker-entrypoint.sh docker-start
  volumes:
    - ../gateway:/etc/bms-gateway:ro
  ports:
    - "${GATEWAY_APISIX_PORT:-9080}:9080"
```

`deploy/gateway/config.yaml`（启动配置，手写）：

```yaml
apisix:
  node_listen: 9080
deployment:
  role: data_plane
  role_data_plane:
    config_provider: yaml
nginx_config:
  error_log_level: warn
```

> **为何目录挂载 + 软链**：Docker **单文件 bind mount** 在宿主文件被替换（`git pull` / 重建，新 inode）后，容器内仍指向旧 inode，APISIX 的 1s 文件轮询读不到新内容、**无法热加载**；改为挂载配置目录并软链进 `conf/`，宿主替换即时可见。

## 4. 声明式配置来源（服务目录） <a id="config"></a>

`deploy/gateway/apisix.yaml` **不是手写件**，由服务目录生成：

| 项 | 说明 |
| --- | --- |
| 单一来源 | 服务目录 `SERVICE_CATALOG`（`backend/libs/bms_core/src/bms_core/services/module_registry.py`） |
| 生成 | `cd backend && uv run python -m ops.gateway_config render`（写出 `deploy/gateway/apisix.yaml`） |
| 校验 | `uv run python -m ops.gateway_config check`（零漂移；CI `base-integrity` 与本地预检同跑） |
| 参与服务 | 仅启用且带服务标识的服务（当前 9 个：platform / identity / tenant / org / file / notification / search / ai / report） |
| 外部路径 | `/api/{service_key}/v1/...`，网关 `proxy-rewrite` 剥离为服务内 `/api/v1/...` |
| 认证 / 限流钩子 | 插件经 `gateway_catalog.py::ROUTE_PLUGINS` 按服务合并；默认不启用（随 04_02 / 04_03 接入） |

**改配置的唯一正确路径**：改服务目录或生成脚本 → `render` 重新生成 → 提交 →（热加载或重建）→ 禁止在控制台手工增删。

## 5. 部署步骤 <a id="deploy"></a>

```bash
# mjpc：同步配置到 mjbk（保持 deploy/ 相对结构：compose/gateway.yml + gateway/）
cd <bms 仓库>/deploy
tar -cz -C . gateway compose/gateway.yml | ssh <SSH账号>@<mjbk-IP> 'tar -xz -C ~/deploy'

# mjbk：与基础设施同项目（compose）拉起，仅启动网关两容器
cd ~/deploy/compose
docker compose -p compose --env-file ../.env -f gateway.yml up -d
```

- 端口经 `~/deploy/.env` 的 `GATEWAY_APISIX_PORT`（默认 9080）与 `GATEWAY_HTTP_PORT`（默认 8088，nginx 用）配置。
- 首次会在 `~/deploy/.env` 追加上述两键（模板见仓库 `deploy/.env.example`）。
- 用 `-p compose` 与既有基础设施同项目、同网络（`compose_default`），后续服务容器化后可直接按服务名寻址；命令会提示既有容器为 orphan（正常，不影响）。

## 6. 验证 <a id="verify"></a>

```bash
docker ps --filter name=bms-apisix
docker logs bms-apisix 2>&1 | tail
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9080/api/<service_key>/v1/<path>   # 命中上游 → 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9080/api/nope/v1/x               # 未登记服务 → 404
```

本次部署结果（2026-09-23）：容器 `bms-apisix` Up，`Server: APISIX/3.18.0`；以 `traefik/whoami` 作临时上游（命名 `platform`、端口 8000，验后移除）实测 `GET /api/platform/v1/ping` 命中上游且被重写为 `GET /api/v1/ping`；未登记服务返回 404；从 mjpc TCP 连通 9080 为 OPEN。

> 当前后端服务尚未容器化，除临时验证外，各服务路由在上游不可达时返回 **502**，属预期（服务容器化与按服务发布归后续任务）。

## 7. 使用说明 <a id="use"></a>

| 项目 | 值 |
| --- | --- |
| 入口地址（直连网关） | `http://<mjbk-IP>:9080`（仅内网） |
| 外部路径约定 | `/api/{service_key}/v1/...`（如 `/api/identity/v1/captcha/...`）→ 服务内 `/api/v1/...` |
| 上游寻址 | Compose DNS 服务名 + 8000（`{service_key}:8000`），禁硬编码 IP |
| 容器名 | `bms-apisix` |
| 配置目录 | mjbk `~/deploy/gateway/`（仓库 `deploy/gateway/`） |
| 防火墙 | 端口经 Docker 发布（走 FORWARD 链），已对 `<内网网段>` 可达（见《[防火墙部署使用说明](防火墙部署使用说明.md)》6.1） |

**热加载**：更新 `~/deploy/gateway/apisix.yaml`（重新生成后同步）后，APISIX 在 1 秒内轮询到变化并热更新，日志出现 `config file …/apisix.yaml reloaded.`，无需重启；整文件替换同样生效。

## 8. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-apisix` |
| 查看日志 | `docker logs -f bms-apisix` |
| 重启 | `docker restart bms-apisix` |
| 停止 / 启动 | `docker compose -p compose -f compose/gateway.yml stop apisix` / `start apisix`（在 `~/deploy/compose`） |
| 重新生成配置 | mjpc：`cd backend && uv run python -m ops.gateway_config render`，再按第 5 节同步 |
| 校验配置零漂移 | `uv run python -m ops.gateway_config check`（CI `base-integrity` 同跑） |
| 升级镜像 | 改 `gateway.yml` 版本标签 → `docker compose … up -d`（锁定版本，勿用 `latest`） |

## 9. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| 改配置不生效 | 宿主替换 `apisix.yaml` 后网关行为不变、日志无 `reloaded` | 单文件 bind mount 仍指向旧 inode；改目录挂载 + 启动软链（见第 3 节），替换即时生效 |
| 镜像标签不存在 | `apache/apisix:3.18.0` 拉取失败 | 官方 Docker 标签为 `apache/apisix:3.18.0-debian` |
| 各服务路由 502 | 访问 `/api/{service}/v1/...` 报 502 | 后端服务尚未容器化 / 未启动（预期）；服务容器化后随编排接入 |
| 提示 orphan containers | `up -d` 时报 `Found orphan containers (…)` | 仅提示既有基础设施容器不在本文件内，正常；勿用 `--remove-orphans`（会误删基础设施） |
| 端口被占 | 9080 已被占用 | 改 `~/deploy/.env` 的 `GATEWAY_APISIX_PORT` 后重建 |

## 10. 关联文档 <a id="related"></a>

- [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)：服务部署总览与端口规划
- [nginx 部署使用说明](nginx部署使用说明.md)：边缘静态托管与 `/api` 分流
- [防火墙部署使用说明](防火墙部署使用说明.md)：端口放行口径（Docker FORWARD 链）
- [KiwiTCMS部署使用说明](KiwiTCMS部署使用说明.md)：同类「mjbk 容器服务」部署实录参照
- 平台《架构设计 · API 网关与边缘》「部署形态与演进」「边缘功能」节
- 平台《微服务演进规划》「技术选型」节
- 平台《部署发布规范》「API 网关配置与热加载」节

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-09-23 实际部署与验证过程
