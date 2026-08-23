# 01-1 mjbk Ubuntu 基础

> 准备期 · 01 环境与工具链 · 子任务 01-1

[文档首页](../../../../文档首页.md) › [01 环境与工具链](../01_环境与工具链.md) › 01-1 mjbk Ubuntu 基础　|　[← 父任务](../01_环境与工具链.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-1 |
| 父任务 | [01 环境与工具链](../01_环境与工具链.md) |
| 对应需求 | [01-1](../../需求/01_需求_环境与工具链.md#r01-1) |
| 禅道任务 | 85（父任务 1） |
| 工时（重估） | 4h |
| 依赖 | 无（准备期首个任务） |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-08-15 |

## 2. 任务内容 <a id="content"></a>

1. Ubuntu 24.04.4 LTS 桌面版，静态 IP（内网段 /24），apt 换清华源
2. SSH 免密：mjpc 公钥录入 mjbk
3. 磁盘挂载：机械盘 `/mnt/data`、2T NVMe SSD `/mnt/ssd2t`（ext4 + fstab 自动挂载）
4. Docker data-root 迁至 `/mnt/ssd2t/docker`（镜像/容器/命名卷全落 NVMe）；GitLab 数据落 `/mnt/ssd2t/gitlab`；机械盘只放备份与 Timeshift 快照（数据与备份分盘）
5. Timeshift 系统快照：每日自动，保留 5 份，落 `/mnt/data/timeshift`

## 3. 完成标准 <a id="accept"></a>

mjpc SSH 免密连通；重启后两块盘自动挂载且 `daemon.json` data-root 生效；Timeshift 可建快照并可回滚。

## 4. 参考文档 <a id="ref"></a>

- 《Ubuntu安装部署使用说明》第 7 节
- 《开发部署规划》4.1/4.2

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-21
