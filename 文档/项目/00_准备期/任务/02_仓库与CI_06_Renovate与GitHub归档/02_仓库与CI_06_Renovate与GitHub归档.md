# 06 Renovate 与 GitHub 归档

> 准备期 · 02 仓库与CI · 子任务 06

[文档首页](../../../../文档首页.md) › [02 仓库与CI](../02_仓库与CI.md) › 06 Renovate 与 GitHub 归档　|　[← 父任务](../02_仓库与CI.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 06 |
| 父任务 | [02 仓库与CI](../02_仓库与CI.md) |
| 对应需求 | [02-6](../../需求/02_需求_仓库与CI.md#r02-6) |
| 工时（重估） | 3h |
| 依赖 | 01、mjbk 外网恢复 |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-08-22T08:50:00Z |

## 2. 任务内容 <a id="content"></a>

1. Renovate：阶段二起以容器方式编排（随 `gitlab.yml`），自动提交依赖升级 MR；安全更新优先
2. GitHub push mirror：GitLab 配置 push mirror，main 单向同步至 GitHub 归档仓库

## 3. 完成标准 <a id="accept"></a>

Renovate 升级 MR 自动提交；main 单向同步至 GitHub 归档仓库成功。

## 4. 参考文档 <a id="ref"></a>

- 《开发部署规划》4.5、《总体项目规划》第 12 节（配置与变更管理）

> 风险口径：mjbk 外网不可达（GitHub 镜像 / Renovate / 镜像拉取）——镜像预缓存，GitHub 归档与 Renovate 暂缓，不影响内网开发主路径（《开发部署规划》第 11 节）。


## 5. 执行记录 <a id="log"></a>

- 2026-08-22：外网复核通过（push mirror 实测一直正常、api.github.com 可达）解除搁置并当日完成——renovate 服务加入 gitlab.yml（platform=gitlab，仓库 mj/bms），试运行 exit=0；cron 每日 06:00 调度；push mirror 经用户确认一直正常同步（GitLab API 不暴露该配置，机制在 UI 层）。过程中处置 GitLab 挂载事故一次（详见《GitLab部署使用说明》事故记录）。
> 本文档依《文档生成规范》编写 · 更新：2026-08-22（完成） · 生成日期：2026-08-21
