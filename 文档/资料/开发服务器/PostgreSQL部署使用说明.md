# PostgreSQL 部署使用说明

> mjbk 备选数据库部署实录 · 2026-08-10

[文档首页](../../文档首页.html) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › PostgreSQL 部署使用说明　|　[← 上一个：MySQL](MySQL部署使用说明.md)　|　[下一个：达梦 DM8 →](达梦DM8部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 PostgreSQL（容器 `bms-postgres`，版本 16）与 MySQL、达梦 DM8 并称「常驻三库」，
用于开发联调与 CI 三库方言测试（《[开发部署规划](../../规划/开发部署规划.html)》4.4）。
`<mjbk-IP>` 取值见《[本地资源](../../用户文档/本地资源.md)》。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/base.yml`：

```yaml
postgres:
  image: postgres:16
  container_name: bms-postgres
  restart: unless-stopped
  environment:
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    TZ: Asia/Shanghai
  ports:
    - "5432:5432"
  volumes:
    - postgres-data:/var/lib/postgresql/data
```

> postgres 超级用户密码来自 `deploy/.env` 的 `POSTGRES_PASSWORD`（随机生成）。
> 数据卷 `postgres-data` 为命名卷（NVMe SSD，`/mnt/ssd2t/docker`）。UTF8 为镜像默认编码。

## 3. 部署步骤 <a id="deploy"></a>

```bash
cd ~/deploy
docker compose -f compose/base.yml --env-file .env up -d postgres
```

> 同样必须带 `--env-file .env`（见《[MySQL部署使用说明](MySQL部署使用说明.md)》第 3 节坑点）。

## 4. 验证 <a id="verify"></a>

```bash
docker exec bms-postgres pg_isready -U postgres     # accepting connections
docker exec bms-postgres psql -U postgres -c "SELECT version();"
```

本次部署结果：版本 **16.14**（Debian 镜像）。

## 5. 数据库与账号规划 <a id="dbs"></a>

| 用途 | 库名 | 说明 |
| --- | --- | --- |
| 开发联调 | `bms_dev`（已创建） | UTF8；按需建平台库/租户库/归档库 |
| CI 集成测试 | `bms_test` 前缀 | job 内建库 → 迁移 → 测试 → 删库 |

- 连接串示例：`postgresql+psycopg://bms_dev:<密码>@<mjbk-IP>:5432/bms_dev`（应用账号部署时创建）

## 6. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-postgres` |
| 查看日志 | `docker logs -f bms-postgres` |
| 进入客户端 | `docker exec -it bms-postgres psql -U postgres` |
| 备份（每日 cron 2 点） | `docker exec bms-postgres pg_dump -U postgres -Fc bms_dev > /mnt/data/backup/postgres/bms_dev-$(date +%F).dump` |
| 现场导出（缺陷重现，见《[测试规范](../../规范/测试规范.html)》9 节） | `mkdir -p /mnt/data/backup/defects/<缺陷号> && docker exec bms-postgres pg_dump -U postgres -Fc <库名> > /mnt/data/backup/defects/<缺陷号>/<库名>.dump` |

## 7. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览
- 《[MySQL部署使用说明](MySQL部署使用说明.md)》：主数据库（同批部署、同构坑点）
- 《[开发部署规划](../../规划/开发部署规划.html)》：4.4 常驻数据库方案
- 《[命名规范](../../规范/命名规范.html)》：库名约定

> 本文档为 AI 生成 · 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程 · 更新日期：2026-08-15