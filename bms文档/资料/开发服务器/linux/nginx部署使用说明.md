# nginx 部署使用说明

> mjbk 边缘静态托管与 API 分流（容器 bms-gateway-nginx）部署实录 · 2026-09-23

[文档首页](../../../文档首页.md) › [资料](../../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md) › nginx 部署使用说明　|　[← 上一个：APISIX](APISIX部署使用说明.md)　|　[总览](开发服务器部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 nginx（容器 `bms-gateway-nginx`）是**边缘静态资源托管与 API 分流**入口：前端静态资源（PC 管理端 / 移动端 H5 产物）由它直接托管，`/api/` 流量反代至边缘网关（[APISIX](APISIX部署使用说明.md)），实现「网关只处理 API」。
本说明记录该容器的编排、配置、部署与运维；`<mjbk-IP>` 取值见《[本地资源](../../../用户文档/本地资源.md)》。

> 范围说明：本容器是**本项目边缘分流用的 nginx**，与 mjbk 上其他用途（如 Kiwi TCMS 容器内置 nginx）无关；生产形态的 TLS / 域名 / CDN 随部署阶段细化。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/gateway.yml`（已同步至 mjbk `~/deploy/compose/gateway.yml`）：

```yaml
gateway-nginx:
  image: nginx:1.27
  container_name: bms-gateway-nginx
  restart: unless-stopped
  depends_on:
    - apisix
  environment:
    TZ: Asia/Shanghai
  volumes:
    - ../gateway/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    - ../gateway/static:/usr/share/nginx/html:ro
  ports:
    - "${GATEWAY_HTTP_PORT:-8088}:80"
```

## 3. 配置说明 <a id="config"></a>

仓库 `deploy/gateway/nginx.conf`（挂载为容器内 `/etc/nginx/conf.d/default.conf`）：

| 位置 | 行为 |
| --- | --- |
| `map $http_upgrade $connection_upgrade` | WebSocket 升级（如 `/socket.io`）；无 `Upgrade` 头时置空，避免误传 `Connection: upgrade` |
| `location /api/` | `proxy_pass http://apisix:9080`，透传 `Host` / `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto` 与 `Upgrade` / `Connection` |
| `location /` | `try_files $uri $uri/ /index.html`（静态托管 + SPA 回退） |
| 安全响应头 | `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` / `Permissions-Policy`（CSP / HSTS 占位，生产随 TLS 启用） |

- **静态目录** `deploy/gateway/static/`：当前为占位首页；**前端构建产物接入归部署阶段**（平台部署阶段交付）。
- **分流口径**：静态资源不经过网关；只有 `/api/` 走网关，网关按服务目录路由到各服务。

## 4. 部署步骤 <a id="deploy"></a>

与 APISIX 同一次编排（同一 `gateway.yml`），步骤见《[APISIX 部署使用说明](APISIX部署使用说明.md)》「部署步骤」节。要点：

```bash
# mjpc：同步（gateway/ 与 compose/gateway.yml 一并）
cd <bms 仓库>/deploy
tar -cz -C . gateway compose/gateway.yml | ssh <SSH账号>@<mjbk-IP> 'tar -xz -C ~/deploy'

# mjbk：与基础设施同项目拉起（含 apisix 与 gateway-nginx）
cd ~/deploy/compose
docker compose -p compose --env-file ../.env -f gateway.yml up -d
```

## 5. 验证 <a id="verify"></a>

```bash
docker ps --filter name=bms-gateway-nginx
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8088/                    # 静态首页 → 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8088/api/nope/v1/x       # 经网关 → 404（未登记服务）
```

本次部署结果（2026-09-23）：容器 `bms-gateway-nginx` Up（`8088->80`）；`GET /` 返回 200；`GET /api/platform/v1/ping`（临时上游）经 nginx → 网关命中上游并重写为 `/api/v1/ping`；从 mjpc TCP 连通 8088 为 OPEN。

## 6. 使用说明 <a id="use"></a>

| 项目 | 值 |
| --- | --- |
| 访问地址 | `http://<mjbk-IP>:8088`（静态 + `/api` 统一入口，仅内网） |
| API 前缀 | `/api/{service_key}/v1/...`（反代至网关，见 [APISIX 说明](APISIX部署使用说明.md) 第 7 节） |
| 容器名 | `bms-gateway-nginx` |
| 静态根 | 容器内 `/usr/share/nginx/html`（挂载 mjbk `~/deploy/gateway/static/`） |
| 配置文件 | mjbk `~/deploy/gateway/nginx.conf`（仓库 `deploy/gateway/nginx.conf`） |
| 防火墙 | 端口经 Docker 发布（走 FORWARD 链），已对 `<内网网段>` 可达（见《[防火墙部署使用说明](防火墙部署使用说明.md)》6.1） |

## 7. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-gateway-nginx` |
| 查看日志 | `docker logs -f bms-gateway-nginx` |
| 重启 | `docker restart bms-gateway-nginx` |
| 重新加载配置 | `docker exec bms-gateway-nginx nginx -s reload`（改 `nginx.conf` 同步后） |
| 更新静态产物 | 将前端构建产物放入 `~/deploy/gateway/static/`（或改挂载点），刷新浏览器 |
| 端口冲突 | 改 `~/deploy/.env` 的 `GATEWAY_HTTP_PORT` 后重建 |

## 8. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| `/api/` 返回 502 | 反代目标不可达 | 网关容器未起 / 上游服务未就绪；先查 `docker ps --filter name=bms-apisix` 与网关日志 |
| 静态 404 | 访问某资源返回 404 | 产物未放入 `~/deploy/gateway/static/`（当前为占位页）；前端产物接入归部署阶段 |
| 端口被占 | 8088 已被占用 | 改 `~/deploy/.env` 的 `GATEWAY_HTTP_PORT` 后重建 |
| 配置改动不生效 | 改 `nginx.conf` 后行为不变 | 需同步到 mjbk 并 `nginx -s reload`（或重建容器） |

## 9. 关联文档 <a id="related"></a>

- [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)：服务部署总览与端口规划
- [APISIX 部署使用说明](APISIX部署使用说明.md)：边缘网关（`/api/` 反代目标）
- [防火墙部署使用说明](防火墙部署使用说明.md)：端口放行口径（Docker FORWARD 链）
- 平台《开发部署规划》「端口与网络规划」节
- 平台《架构设计 · 部署与运维》「部署拓扑」「集群设计要点」节

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-09-23 实际部署与验证过程
