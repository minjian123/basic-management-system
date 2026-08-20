# MySQL 部署使用说明

> mjbk 主数据库部署实录 · 2026-08-10

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › MySQL 部署使用说明　|　[← 上一个：Redis](Redis部署使用说明.md)　|　[下一个：PostgreSQL →](PostgreSQL部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 MySQL（容器 `bms-mysql`，版本 8.4）是 BMS 开发环境主数据库，
常驻供开发联调与 CI 三库方言测试复用（《[开发部署规划](../../规划/开发部署规划.md)》4.4）。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/base.yml`：

```yaml
mysql:
  image: mysql:8.4
  container_name: bms-mysql
  restart: unless-stopped
  environment:
    MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    TZ: Asia/Shanghai
  ports:
    - "3306:3306"
  volumes:
    - mysql-data:/var/lib/mysql
  command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

> root 密码来自 `deploy/.env` 的 `MYSQL_ROOT_PASSWORD`（随机生成，仅存 mjbk）。
> 数据卷 `mysql-data` 为命名卷（NVMe SSD，`/mnt/ssd2t/docker`），字符集强制 `utf8mb4 / utf8mb4_unicode_ci`。

## 3. 部署步骤 <a id="deploy"></a>

```bash
cd ~/deploy
docker compose -f compose/base.yml --env-file .env up -d mysql
```

> 坑点：必须带 `--env-file .env`。用 `-f compose/base.yml` 时 Compose 默认不会读取
> `~/deploy/.env`，`${MYSQL_ROOT_PASSWORD}` 展开为空，容器会以
> 「Database is uninitialized and password option is not specified」循环重启。

## 4. 验证 <a id="verify"></a>

```bash
docker exec bms-mysql mysqladmin ping -uroot -p"$密码"   # mysqld is alive
docker exec bms-mysql mysql -uroot -p"$密码" -e "SELECT VERSION();"
docker exec bms-mysql mysql -uroot -p"$密码" -e "SHOW VARIABLES LIKE 'character_set_server';"
```

本次部署结果：版本 **8.4.11**，字符集 `utf8mb4`，排序 `utf8mb4_unicode_ci`。

## 5. 数据库与账号规划 <a id="dbs"></a>

| 用途 | 库名 | 说明 |
| --- | --- | --- |
| 开发联调 | `bms_dev`（已创建） | utf8mb4；后续按需建 `bms_platform`、`bms_tenant_*`、`bms_archive` 模拟多租户拓扑 |
| CI 集成测试 | `bms_test` 前缀 | job 内建库 → 迁移 → 测试 → 删库，与开发数据隔离 |

- 应用账号（非 root）由后端部署时创建，遵循《[命名规范](../../规范/命名规范.md)》库名/账号约定。
- 密码只存在于 `~/deploy/.env`，不入库、不入文档。

## 6. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-mysql` |
| 查看日志 | `docker logs -f bms-mysql` |
| 重启 | `docker restart bms-mysql` |
| 进入客户端 | `docker exec -it bms-mysql mysql -uroot -p` |
| 备份（每日 cron 2 点） | `mysqldump --single-transaction -uroot -p"$密码" bms_dev > /mnt/data/backup/mysql/bms_dev-$(date +%F).sql` |
| 现场导出（缺陷重现，见《[测试规范](../../规范/测试规范.md)》9 节） | `mkdir -p /mnt/data/backup/defects/<缺陷号> && mysqldump --single-transaction -uroot -p"$密码" <库名> > /mnt/data/backup/defects/<缺陷号>/<库名>.sql` |

## 7. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| root 密码为空导致重启循环 | 容器 `Restarting (1)`，日志报「Database is uninitialized and password option is not specified」 | 原因：compose 未读到 `.env`。改用 `--env-file .env` 重新 up；`docker compose down mysql` 后重建（数据卷为空，无残留数据问题） |

## 8. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览
- 《[DockerEngine部署使用说明](DockerEngine部署使用说明.md)》：容器引擎
- 《[PostgreSQL部署使用说明](PostgreSQL部署使用说明.md)》：备选数据库
- 《[开发部署规划](../../规划/开发部署规划.md)》：4.4 常驻数据库方案
- 《[命名规范](../../规范/命名规范.md)》：库名约定（bms_dev / bms_test 前缀）

> 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程 · 更新日期：2026-08-15