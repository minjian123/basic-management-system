# Keycloak 部署使用说明

> mjbk 自托管 OIDC IdP（Keycloak 26.7.4）部署实录 · 2026-09-23

[文档首页](../../../文档首页.md) › [资料](../../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md) › Keycloak 部署使用说明　|　[同级：APISIX 部署使用说明 →](APISIX部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 Keycloak（容器 `bms-keycloak`）是平台的**自托管 OIDC 身份源（IdP）**：为网关与后端服务提供统一的用户 / 服务身份签发与 **JWKS 公钥分发**（BMS 作为 OIDC 客户端经 Discovery 发现并验签）。本文档记录其**部署形态、声明式配置来源、部署步骤、验证与运维**；认证业务（登录链路 / RBAC / JIT 建号）见认证阶段设计，不在本文。

**取值说明**：`<mjbk-IP>` / `<SSH账号>` 等占位符取值见《[本地资源](../../../用户文档/本地资源.md)》与 mjbk `deploy/.env`；真实凭据只写 `deploy/.env`（`.env.example` 入仓库），不入本文档。

## 2. 部署形态 <a id="shape"></a>

- **镜像**：`quay.io/keycloak/keycloak:26.7.4`（固定 tag；国内拉取走 Docker 镜像加速器）。
- **模式**：`start --import-realm --http-enabled=true --health-enabled=true`（非 dev 模式，元数据持久化）。
- **元数据库**：复用 `bms-postgres` 容器，**独立库 `keycloak`** 与独立角色 `keycloak`。
- **realm / 客户端**：声明式 `deploy/keycloak/bms-realm.json`（realm `bms` + confidential 客户端 `bms-backend`），启动自动导入（已存在则跳过）。
- **暴露**：宿主端口 `${KEYCLOAK_PORT:-8090}` → 容器 8080；**不经业务网关（APISIX）**，属基础设施身份源。
- **健康端点**：管理端口 9000 的 `/health/ready`（容器 healthcheck 探活）。

## 3. Compose 配置 <a id="compose"></a>

编排文件 `deploy/compose/keycloak.yml`（与 `base.yml` 组合；服务名即 DNS 名）：

```yaml
services:
  keycloak:
    image: quay.io/keycloak/keycloak:26.7.4
    container_name: bms-keycloak
    command: [start, --import-realm, --http-enabled=true, --health-enabled=true]
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: ${KEYCLOAK_DB_USERNAME:-keycloak}
      KC_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD}
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KEYCLOAK_ADMIN_USERNAME:-admin}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD}
      KC_HTTP_PORT: 8080
      KC_HOSTNAME: ${KEYCLOAK_PUBLIC_URL:-http://localhost:8090}
      KC_HOSTNAME_STRICT: "false"
      KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_CLIENT_SECRET}   # 供 realm 导入占位解析
    ports:
      - "${KEYCLOAK_PORT:-8090}:8080"
    volumes:
      - ../keycloak:/opt/keycloak/data/import:ro
```

- **`KC_HOSTNAME` = 访问基址**：issuer 固定为 `<KC_HOSTNAME>/realms/bms`；远端访问须把 `KEYCLOAK_PUBLIC_URL` 设为 `http://<mjbk-IP>:8090`（与后端 `[identity_provider].issuer` 一致），否则令牌 `iss` 校验失败。
- **`KC_HOSTNAME_STRICT=false`**：允许以其它主机名（内网 IP / localhost）访问控制台，issuer 仍按 `KC_HOSTNAME` 固定。

## 4. 声明式配置来源 <a id="config"></a>

| 来源 | 作用 |
| --- | --- |
| `deploy/keycloak/bms-realm.json` | realm `bms` 与 OIDC 客户端 `bms-backend`（`standardFlowEnabled` 授权码 + `serviceAccountsEnabled` 服务账号）；client secret 为 `${KEYCLOAK_CLIENT_SECRET}` 占位 |
| `deploy/postgres/init/01-keycloak.sh` | 首次初始化 postgres 新卷时创建 `keycloak` 角色与库（存量实例手动执行一次，见第 5 节） |
| `deploy/compose/keycloak.yml` | 容器编排（见第 3 节） |

- **凭据外部化**：管理员 / 元数据库 / 客户端 secret 全部经 `deploy/.env` 注入；realm JSON 内**无明文密钥**（仅占位符）。
- **客户端 secret 一致性**：`deploy/.env` 的 `KEYCLOAK_CLIENT_SECRET` 须与后端 `BMS_IDENTITY_PROVIDER__CLIENT_SECRET` 一致。

## 5. 部署步骤 <a id="deploy"></a>

```bash
# mjpc：同步部署件到 mjbk（保持 deploy/ 相对结构）
rsync -av bms/deploy/compose/keycloak.yml bms/deploy/keycloak bms/deploy/postgres bms/deploy/.env \
      <SSH账号>@<mjbk-IP>:~/deploy/

# mjbk：存量 postgres 实例需先建 keycloak 角色与库（新卷由 initdb 自动执行，可跳过）
docker exec -i bms-postgres psql -U postgres <<'SQL'
SELECT 'CREATE ROLE keycloak LOGIN PASSWORD ' || quote_literal('<<KEYCLOAK_DB_PASSWORD>>')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak')\gexec
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec
SQL

# mjbk：与基础设施同项目（compose）拉起
cd ~/deploy
docker compose -f compose/base.yml -f compose/keycloak.yml --env-file .env up -d keycloak
```

## 6. 验证 <a id="verify"></a>

```bash
# 容器健康
docker inspect --format '{{.State.Health.Status}}' bms-keycloak     # healthy

# Discovery 文档（issuer 应为配置基址）
curl -s "http://<mjbk-IP>:8090/realms/bms/.well-known/openid-configuration" | jq '{issuer, jwks_uri, token_endpoint}'

# JWKS 公钥
curl -s "http://<mjbk-IP>:8090/realms/bms/protocol/openid-connect/certs" | jq '.keys | length'

# 服务账号取令牌（client_credentials）→ 得到 JWT
TOKEN=$(curl -s -X POST "http://<mjbk-IP>:8090/realms/bms/protocol/openid-connect/token" \
  -d grant_type=client_credentials -d client_id=bms-backend -d "client_secret=${KEYCLOAK_CLIENT_SECRET}" | jq -r .access_token)
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{iss, sub, exp}'
```

- **JWKS 验签通过（本任务验收）**：以 `OidcIdentityProvider.verify_token(token)` 经 JWKS 验签并校验 `exp` / `iss`；集成用例见 `backend/services/identity/tests/idp/test_oidc.py`（`IDP_TEST_*` 环境变量开启，未配置跳过）。

## 7. 使用说明 <a id="use"></a>

| 项 | 取值 |
| --- | --- |
| issuer | `http://<mjbk-IP>:8090/realms/bms` |
| Discovery | `<issuer>/.well-known/openid-configuration` |
| JWKS | `<issuer>/protocol/openid-connect/certs` |
| 授权端点 | `<issuer>/protocol/openid-connect/auth` |
| 令牌端点 | `<issuer>/protocol/openid-connect/token` |
| 管理控制台 | `http://<mjbk-IP>:8090/admin`（管理员账号见 `deploy/.env`） |
| 后端接入 | `[identity_provider].provider = "oidc"`，`issuer` 同上，`client_secret` 经 `BMS_IDENTITY_PROVIDER__CLIENT_SECRET` 注入 |

## 8. 日常运维 <a id="ops"></a>

```bash
docker logs -f bms-keycloak                     # 日志
docker compose -f compose/base.yml -f compose/keycloak.yml restart keycloak
docker inspect --format '{{.State.Health.Status}}' bms-keycloak
```

- **realm 变更**：`--import-realm` 对已存在 realm **跳过导入**（不覆盖），避免重启丢状态；变更经控制台修改后须回写 `bms-realm.json` 并显式 `import --override`（或重建库）以对齐仓库。声明式配置为**唯一来源**，禁止只改控制台不回写。
- **升级**：改 `keycloak.yml` 镜像 tag → 重新拉起；升级前备份 `keycloak` 库。

## 9. 排障记录 <a id="trouble"></a>

| 现象 | 原因 / 处置 |
| --- | --- |
| 启动报连库失败 | `keycloak` 库 / 角色未建（存量实例）：执行第 5 节建库命令 |
| 令牌 `iss` 校验失败 | `KEYCLOAK_PUBLIC_URL` / 后端 `issuer` 与访问基址不一致：统一为实际访问地址 |
| 控制台可访问但 Discovery issuer 为 localhost | `KC_HOSTNAME` 未设为实际访问地址：改 `KEYCLOAK_PUBLIC_URL` 后重启 |
| 内部 HTTPS 要求（`sslRequired=external`） | 私有网段（`10.x` / `172.16-31.x` / `192.168.x` / 回环）视为内部、允许 HTTP；生产配 TLS 与域名 |
| 镜像拉取缓慢 | 经 Docker 镜像加速器拉取（见《[DockerEngine部署使用说明](DockerEngine部署使用说明.md)》） |

## 10. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)》：端口规划与服务清单
- 《[PostgreSQL部署使用说明](PostgreSQL部署使用说明.md)》：元数据库
- 《[DockerEngine部署使用说明](DockerEngine部署使用说明.md)》：容器引擎与镜像加速
- 《[部署发布规范](../../../规范/部署发布规范.md)》「身份源（IdP）编排与凭据外部化」节
- Keycloak 官方文档：[Importing and exporting realms](https://www.keycloak.org/server/importExport) · [Configuring the database](https://www.keycloak.org/server/db)

> 依《文档生成规范》编写 · 服务部署随进度逐项补充
