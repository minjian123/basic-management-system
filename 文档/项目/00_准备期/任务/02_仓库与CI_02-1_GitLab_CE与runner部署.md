# 02-1 GitLab CE 与 runner 部署

> 准备期 · 02 仓库与CI · 子任务 02-1

[文档首页](../../../文档首页.md) › [02 仓库与CI](02_仓库与CI.md) › 02-1 GitLab CE 与 runner 部署　|　[← 父任务](02_仓库与CI.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 02-1 |
| 父任务 | [02 仓库与CI](02_仓库与CI.md) |
| 对应需求 | [02-1](../需求/02_需求_仓库与CI.md#r02-1) |
| 禅道任务 | 待建（父任务 2） |
| 工时（重估） | 4h |
| 依赖 | 01-2 |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-08-15 |

## 2. 任务内容 <a id="content"></a>

1. GitLab CE 容器（`deploy/compose/gitlab.yml`）：HTTP 8080、Registry 5050、SSH 2222；数据目录挂载 `/mnt/ssd2t/gitlab`
2. gitlab-runner 容器：executor=docker（挂载宿主机 docker.sock），image `python:3.14-slim`，tag `bms,docker`
3. runner 并发限制 `concurrent = 2`（mjbk 6 核 12 线程，避免 CI 挤占 GitLab 与开发服务）

## 3. 完成标准 <a id="accept"></a>

GitLab Web 可访问（8080）；runner 注册并在线，测试 job 可运行。

## 4. 参考文档 <a id="ref"></a>

- 《GitLab部署使用说明》
- 《开发部署规划》4.5

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-21
