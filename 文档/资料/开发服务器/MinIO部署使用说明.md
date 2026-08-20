# MinIO 部署使用说明

> mjbk 对象存储部署实录 · 2026-08-10

[文档首页](../../文档首页.html) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › MinIO 部署使用说明　|　[← 上一个：PostgreSQL](PostgreSQL部署使用说明.md)　|　[下一个：GitLab →](GitLab部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 MinIO（容器 `bms-minio`）提供 S3 兼容对象存储，承载 BMS 文件管理、
归档冷化对象与 Milvus（阶段十四）数据，是开发依赖服务之一（《[开发部署规划](../../规划/开发部署规划.html)》4.3 base 组）。
`<mjbk-IP>` 取值见《[本地资源](../../用户文档/本地资源.md)》。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/base.yml`：

```yaml
minio:
  image: minio/minio:latest
  container_name: bms-minio
  restart: unless-stopped
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
  ports:
    - "9000:9000"
    - "9001:9001"
  volumes:
    - minio-data:/data
```

> root 账号来自 `deploy/.env`（`MINIO_ROOT_USER=minioadmin`，密码随机）。
> 数据卷 `minio-data` 为命名卷（NVMe SSD，`/mnt/ssd2t/docker`）。9000 为 S3 API，9001 为控制台。

## 3. 部署步骤 <a id="deploy"></a>

```bash
cd ~/deploy
docker compose -f compose/base.yml --env-file .env up -d minio
```

## 4. 验证 <a id="verify"></a>

```bash
curl -s http://<mjbk-IP>:9000/minio/health/live -o /dev/null -w "%{http_code}"   # 200
docker exec bms-minio mc alias set local http://127.0.0.1:9000 minioadmin "<密码>"
docker exec bms-minio mc ls local
```

本次部署结果：API 与控制台均 200，mc 客户端可访问，`bms-files` 桶已创建。

## 5. 使用说明（bucket 规划） <a id="use"></a>

bucket 命名遵循《[命名规范](../../规范/命名规范.html)》：小写连字符，按租户前缀隔离。

| bucket | 用途 | 状态 |
| --- | --- | --- |
| `bms-files` | BMS 文件管理模块（默认） | 已创建 |
| `bms-backup` | 数据备份存储（规划，按需创建） | 待创建 |
| `bms-{租户}` | 按租户隔离 bucket | 租户开通时创建 |

- 控制台：`http://<mjbk-IP>:9001`（root 凭据见 `~/deploy/.env`）
- 访问地址（后端配置）：`http://<mjbk-IP>:9000`

## 6. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-minio` |
| 查看日志 | `docker logs -f bms-minio` |
| mc 操作 | `docker exec bms-minio mc ls local`（alias 已配 `local`） |
| 创建桶 | `docker exec bms-minio mc mb -p local/bms-backup` |
| 重启 | `docker restart bms-minio` |

## 7. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览
- 《[DockerEngine部署使用说明](DockerEngine部署使用说明.md)》：容器引擎与镜像加速（DaoCloud 白名单限制说明）
- 《[开发部署规划](../../规划/开发部署规划.html)》：4.3 服务清单
- 《[命名规范](../../规范/命名规范.html)》：MinIO bucket 命名约定

> 本文档为 AI 生成 · 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程 · 更新日期：2026-08-15