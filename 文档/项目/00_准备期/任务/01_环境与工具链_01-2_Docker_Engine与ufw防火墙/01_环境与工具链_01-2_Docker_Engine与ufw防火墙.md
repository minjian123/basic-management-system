# 01-2 Docker Engine 与 ufw 防火墙

> 准备期 · 01 环境与工具链 · 子任务 01-2

[文档首页](../../../../文档首页.md) › [01 环境与工具链](../01_环境与工具链.md) › 01-2 Docker Engine 与 ufw 防火墙　|　[← 父任务](../01_环境与工具链.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-2 |
| 父任务 | [01 环境与工具链](../01_环境与工具链.md) |
| 对应需求 | [01-2](../../需求/01_需求_环境与工具链.md#r01-2) |
| 禅道任务 | 86（父任务 1） |
| 工时（重估） | 2h |
| 依赖 | 01-1 |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-08-15 |

## 2. 任务内容 <a id="content"></a>

1. Docker Engine 走清华 docker-ce 源安装（docker-ce + buildx + compose 插件），systemd 自启
2. 镜像加速：`/etc/docker/daemon.json` 配置国内 registry-mirrors
3. ufw 防火墙：仅放行内网段服务端口（GitLab 8080/5050/2222、三库 3306/5432/5236、Redis 6379、MinIO 9000/9001、Kiwi 8060、禅道 8070 等，完整清单见《开发部署规划》第 9 节），`ufw enable`

## 3. 完成标准 <a id="accept"></a>

`docker info` / `docker compose version` 通过；mjpc 可连通已放行的内网端口。

## 4. 参考文档 <a id="ref"></a>

- 《DockerEngine部署使用说明》
- 《开发部署规划》4.1/4.6/9

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-21
