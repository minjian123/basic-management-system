# Renovate 技术介绍

> 依赖自动升级 · 自动提 MR 的更新机器人

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › Renovate 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Renovate** 是自动化依赖更新机器人：识别仓库里的各类依赖声明
（package.json、pyproject.toml、Dockerfile、Compose 镜像标签等），
发现新版本后**自动开分支、提 Merge Request**，
由 CI 验证、人工评审合入。它原生支持自托管 GitLab，
是「依赖升级 + 安全补丁」这条流水线的标准答案。

- **定位**：BMS 依赖自动升级，自动提 MR 升级依赖（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）。
- **版本**：3x.x 系列（持续快速迭代）。
- **许可**：AGPL-3.0。BMS 自托管运行、不修改源码，无传染影响（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：阶段二起以容器方式随 gitlab.yml 编排在 mjbk 运行，需 mjbk 可访问外网（《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| manager | 依赖识别器：npm、pip、Docker、Compose、Terraform 等几十种声明格式都能认 |
| branch / MR | 每个升级动作开一个分支并提 MR（GitLab 平台），CI 跑完人再合入 |
| grouping | 把多个小版本升级合并成一个 MR（如「deps: 升级 5 个 npm 包」），防 MR 刷屏 |
| schedule | 限定升级时间窗（如工作日白天），避免半夜提 MR 没人看 |
| automerge | CI 通过后自动合入；BMS 建议保持人工评审，仅对低风险依赖开放 |
| labels | 自动给 MR 打标签（renovate / 依赖类型 / 安全更新），便于过滤与统计 |
| platform | 目标平台：GitHub、GitLab（含自托管）等，BMS 用自托管 GitLab |
| hostRules | 私有仓库 / 私有 registry 的鉴权配置（token 走 CI 变量，不落配置文件） |
| packageRules | 按包 / 按范围定制策略：某包只升补丁、某包禁用自动升级等 |
| 安全更新 | 识别含安全公告（advisory）的版本，单独提「security」MR，优先级更高 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **依赖自动升级**：Python（pyproject / uv.lock）、前端（package.json / lockfile）、容器镜像标签统一由 Renovate 提 MR，CI 验证后人工合入（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **安全补丁通道**：与 GitLab Dependency Scanning 互补——扫描发现漏洞、Renovate 提安全更新 MR（《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节安全专项）。
- **运行方式**：阶段二起以容器方式随 gitlab.yml 编排，常驻 mjbk；需 mjbk 可访问外网（拉取版本发布信息），不可达时镜像同步与依赖升级暂缓（《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节、11 节）。
- **边界**：Renovate 只提 MR 不改代码，合入与否由 CI 门禁 + 人工评审决定，与 main 保护分支策略一致。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Renovate（选中）** | 优点：事实标准、原生支持自托管 GitLab、manager 覆盖全、规则灵活；缺点：需自己跑服务（BMS 已容器化，成本可忽略） | 自托管 GitLab 场景下依赖升级的最优解 |
| Dependabot | 优点：GitHub 内置零配置；缺点：只服务 GitHub，不支持自托管 GitLab | BMS 主仓库在自托管 GitLab，不适用 |
| 人工升级 | 优点：无额外组件；缺点：易遗漏、安全补丁滞后、无审计轨迹 | 安全与效率都不达标，仅作为兜底 |
| audit 类工具（npm audit / pip-audit） | 优点：轻量、查漏洞快；缺点：只报告不修复，不产生升级 MR | 与 Renovate 互补（发现 vs 修复），不替代 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **AGPL 边界**：作为独立服务运行、不改源码、不深度定制，遵守《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节约束。
- **外网依赖**：Renovate 要访问版本发布源与 GitLab API，mjbk 外网不可达时升级暂停，属预期行为（《[开发部署规划](../../../规划/开发部署规划.md#risk)》11 节）。
- **MR 刷屏**：默认每个包一个 MR，包多的仓库会刷屏——用 grouping + schedule 收敛。
- **automerge 风险**：自动合入绕过人工评审，BMS 默认关闭，仅对低风险依赖（如 dev 工具链）谨慎开放。
- **token 权限**：需要创建分支 / MR 的权限，token 走 CI 变量（masked + protected），不落配置文件、不入库。
- **lockfile 一致性**：升级 MR 必须带 lockfile 更新且 CI 通过，防止「提了 MR 但装不上」。
- **Windows 与 Linux 差异**：Renovate 为 Node.js 服务，生产按 Linux 容器运行；Windows 本地调试请用 Docker。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Renovate 官网 | https://renovatebot.com/ | 项目入口、特性与自托管说明 |
| Renovate 官方文档 | https://docs.renovatebot.com/ | 配置项、platform（GitLab）、packageRules 完整参考 |
| Renovate 源码 | https://github.com/renovatebot/renovate | 源码与 issue 讨论 |
| Renovate 官方博客 | https://renovatebot.com/blog/ | 新版本特性与最佳实践 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（依赖升级条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | 选型说明：原生支持自托管 GitLab、自动提 MR |
| 《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节 | mjbk 运行形态：随 gitlab.yml 编排、外网依赖 |
| 《[GitLab 技术介绍](GitLab技术介绍.md)》 | Renovate 提 MR 的目标平台与 CI 验证链路 |
| 《[uv 技术介绍](../工程化与质量/uv技术介绍.md)》 | Python 依赖与 lockfile：升级 MR 的验证对象 |
| 《[npm 技术介绍](../前端/npm技术介绍.md)》 | 前端依赖与 lockfile：升级 MR 的验证对象 |
| 《[Docker 与 Compose 技术介绍](Docker与Compose技术介绍.md)》 | 容器镜像标签升级与 Renovate 的 Docker manager |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19