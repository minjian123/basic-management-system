# 02-6 Renovate 与 GitHub 归档

> 准备期 · 02 仓库与CI · 子任务 02-6

[文档首页](../../../文档首页.md) › [02 仓库与CI](02_仓库与CI.md) › 02-6 Renovate 与 GitHub 归档　|　[← 父任务](02_仓库与CI.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 02-6 |
| 父任务 | [02 仓库与CI](02_仓库与CI.md) |
| 对应需求 | [02-6](../需求/02_需求_仓库与CI.md#r02-6) |
| 禅道任务 | 待建（父任务 2） |
| 工时（重估） | 3h |
| 依赖 | 02-1、mjbk 外网恢复 |
| 负责人 | minjian |
| 状态 | 搁置（mjbk 外网不可达） |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. Renovate：阶段二起以容器方式编排（随 `gitlab.yml`），自动提交依赖升级 MR；安全更新优先
2. GitHub push mirror：GitLab 配置 push mirror，main 单向同步至 GitHub 归档仓库

## 3. 完成标准 <a id="accept"></a>

Renovate 升级 MR 自动提交；main 单向同步至 GitHub 归档仓库成功。

## 4. 参考文档 <a id="ref"></a>

- 《开发部署规划》4.5、《总体项目规划》第 12 节（配置与变更管理）

> 风险口径：mjbk 外网不可达（GitHub 镜像 / Renovate / 镜像拉取）——镜像预缓存，GitHub 归档与 Renovate 暂缓，不影响内网开发主路径（《开发部署规划》第 11 节）。

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-21
