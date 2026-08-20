# Redis 部署使用说明

> mjbk 缓存服务部署实录 · 2026-08-10

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › Redis 部署使用说明　|　[← 上一个：Docker Engine](DockerEngine部署使用说明.md)　|　[下一个：MySQL →](MySQL部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 Redis（容器 `bms-redis`）承载 BMS 的缓存、token 黑名单、分布式锁、限流计数等，
是开发依赖服务之一（《[开发部署规划](../../规划/开发部署规划.md)》4.3 base 组）。
`<mjbk-IP>` 取值见《[本地资源](../../用户文档/本地资源.md)》。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/base.yml`（已同步至 mjbk `~/deploy/compose/base.yml`）：

```yaml
redis:
  image: redis:8
  container_name: bms-redis
  restart: unless-stopped
  ports:
    - "6379:6379"
  volumes:
    - redis-data:/data
  command: redis-server --appendonly yes
```

> 数据卷 `redis-data` 为 Docker 命名卷（存 NVMe SSD `/mnt/ssd2t/docker/volumes`，data-root 已迁移），
> 开启 AOF 持久化（`--appendonly yes`）。命名规范：容器名 `bms-组件`。

## 3. 部署步骤 <a id="deploy"></a>

```bash
# mjbk 上（deploy 目录已同步）
cd ~/deploy
docker compose -f compose/base.yml up -d redis
```

## 4. 验证 <a id="verify"></a>

```bash
docker ps --filter name=bms-redis
redis-cli -h <mjbk-IP> -p 6379 ping   # 返回 PONG
docker exec bms-redis redis-cli INFO persistence  # aof_enabled:1
```

本次部署结果：`PONG`，AOF 开启，RDB 备份正常。

## 5. 使用说明 <a id="use"></a>

| 项目 | 值 |
| --- | --- |
| 连接地址 | `redis://<mjbk-IP>:6379/0`（内网，无密码，仅 ufw 内网放行） |
| 容器名 | `bms-redis` |
| 数据持久化 | AOF（appendonly）+ RDB 快照，数据卷 `redis-data` |

> 开发环境未设密码（内网防火墙隔离）。BMS 的 Redis key 遵循《[命名规范](../../规范/命名规范.md)》：`bms:{租户|global}:{域}:{业务键}`。

## 6. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-redis` |
| 查看日志 | `docker logs -f bms-redis` |
| 重启 | `docker restart bms-redis` |
| 进入客户端 | `docker exec -it bms-redis redis-cli` |
| 清除全部缓存（慎用） | `docker exec bms-redis redis-cli FLUSHALL` |

## 7. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览
- 《[DockerEngine部署使用说明](DockerEngine部署使用说明.md)》：容器引擎
- 《[开发部署规划](../../规划/开发部署规划.md)》：4.3 服务清单与磁盘规划
- 《[命名规范](../../规范/命名规范.md)》：Redis key 约定

> 本文档为 AI 生成 · 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程 · 更新日期：2026-08-15