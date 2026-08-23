# GitLab 技术介绍

> 自托管代码托管 + CI/CD 一体 · BMS 研发协作中枢

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › GitLab 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**GitLab CE**（Community Edition）是自托管 DevOps 平台：
Git 仓库、Merge Request、Issue、CI/CD 流水线、容器 Registry、Wiki
一个平台全包，是「代码托管 + 持续集成」一体的事实标准之一。
**gitlab-runner** 是配套的流水线执行器：注册到 GitLab 后，
按 `.gitlab-ci.yml` 的定义实际跑 job，支持 docker / shell / kubernetes 等执行器。

- **定位**：BMS 研发协作中枢——代码仓库、MR、CI 流水线、镜像 Registry 一体（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）；仅作开发与 CI 基础设施，不随产品交付。
- **版本**：GitLab CE 1x.x 系列（每年 3 个大版本）；gitlab-runner 1x.x 系列。
- **许可**：MIT，免费开源（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：mjbk 自托管（HTTP 8080 + Registry 5050 + SSH 2222），runner 以容器方式运行（《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 仓库 / 分支 | 代码与 git 分支模型；BMS 约定 main 保护分支 + feature/xxx 开发分支 |
| Merge Request | 合并请求：代码评审 + CI 门禁 + 合入 main 的唯一通道 |
| 保护分支 | main 禁止直推，必须经 MR 且 CI 通过才能合入 |
| pipeline | 一次 push / MR 触发的完整流水线，由若干 stage 串联 |
| stage / job | 阶段与任务：`.gitlab-ci.yml` 里声明，job 是执行的最小单位 |
| runner | 执行器：从 GitLab 领取 job 并实际运行，BMS 用 docker 执行器 |
| executor=docker | 每个 job 跑在一次性容器里，环境干净可复现；runner 容器挂载 docker.sock 实现「容器里跑容器」 |
| artifact | job 产物（Allure 报告、构建包、swagger.json），可下载可归档 |
| cache | 跨 job 复用依赖缓存（uv / npm），加速流水线 |
| Registry | 内置容器镜像仓库（BMS 端口 5050），main 流水线构建镜像推送于此 |
| push mirror | 单向镜像同步：BMS 用它把 main 只读同步到 GitHub 归档 |
| CI 变量 | 流水线级密钥与参数，masked（脱敏）+ protected（仅保护分支）双重保护 |
| Dependency Scanning | 内置依赖漏洞扫描模板，与 Renovate 安全更新互补 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **代码托管 + 协作**：仓库、MR、Issue（缺陷载体）一体；Kiwi TCMS 缺陷链接指向 GitLab Issue（《[项目规划说明](../../../规划/项目规划说明.md#test-defect)》16.2 节）。
- **CI 流水线**：`.gitlab-ci.yml` 定义——MR 流水线：后端 ruff + pytest（含覆盖率门禁）、前端 ESLint + Vitest（含 coverage 门禁）、双端构建；main 流水线：另含 Playwright E2E 独立 job、MySQL/PostgreSQL/达梦 DM8 三库方言集成测试、构建镜像推送 Registry、导出 swagger.json 契约快照（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **runner 配置**：gitlab-runner 以容器方式运行，挂载 docker.sock、executor=docker，开发环境并发上限 2，避免 CI 抢占 GitLab 与开发服务资源（《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节）。
- **测试归档**：Allure 报告作 CI 产物归档，执行结果经官方插件导入 Kiwi TCMS（《[项目规划说明](../../../规划/项目规划说明.md#test-report)》16.5 节）。
- **缺陷自动上报**：任一自动化测试失败即由 `scripts/defect/defect_capture.py` 归档 REPRO 复现包并自动创建 / 复用 GitLab Issue（fingerprint 去重）（《[项目规划说明](../../../规划/项目规划说明.md#test-defect)》16.2 节）。
- **GitHub 只读归档**：GitLab 配置 push mirror 单向同步 main 至 GitHub 归档仓库，GitHub 侧改动不回传、不承载协作（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **依赖升级**：Renovate 原生支持自托管 GitLab，自动提 MR 升级依赖（见《[Renovate 技术介绍](Renovate技术介绍.md)》）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **GitLab CE + gitlab-runner（选中）** | 优点：代码 / MR / CI / Registry 一体、自托管成熟、MIT 许可；缺点：内存开销大（≥4GB）、功能面广需配置 | 自托管 DevOps 事实标准，BMS 全链路需求一次满足 |
| GitHub Actions | 优点：SaaS 省心、生态大；缺点：核心服务不可自托管（Enterprise Server 商业收费）、数据出域 | 数据不出域 + 自托管是硬约束，不采用 |
| Gitea | 优点：轻量、资源占用小；缺点：CI 能力弱、MR 体验与生态不如 GitLab | 够用但天花板低，CI 需求下不如 GitLab |
| Jenkins | 优点：老牌、插件极多；缺点：配置以 Groovy / XML 为主、学习曲线陡、界面陈旧 | 维护成本高，新项目无必要 |
| Bitbucket | 优点：Atlassian 生态集成好；缺点：商业收费、自托管受限 | 成本与自托管约束下不采用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **external_url**：首次部署必须配对外访问地址，否则 GitLab 生成的仓库 / 克隆 URL 不正确（《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节）。
- **内存 ≥4GB**：GitLab 是内存大户，mjbk 32GB 预算内单独留足，部署后监控实际占用。
- **runner 并发**：config.toml 设 `concurrent = 2`，CI 重负载不抢占开发服务资源。
- **docker.sock 安全**：runner 容器挂载 docker.sock 等于拿到宿主 root，只给 runner，不给其他容器。
- **Registry 镜像膨胀**：多架构 / 多标签会占盘，定期清理无用 tag，镜像落 NVMe SSD。
- **push mirror 单向**：GitHub 侧只读归档，别在 GitHub 上改动，回传机制不存在。
- **Windows 与 Linux 差异**：开发机（Windows）用 Git for Windows + 浏览器操作 GitLab，本地不跑 GitLab 服务；流水线一律按 Linux 容器口径。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| GitLab 官网 | https://about.gitlab.com/ | 产品入口、版本说明、许可 |
| GitLab 官方文档 | https://docs.gitlab.com/ | 自托管安装、CI/CD、Registry 完整参考 |
| CI/CD 文档 | https://docs.gitlab.com/ee/ci/ | `.gitlab-ci.yml` 语法、runner、artifact 权威参考 |
| GitLab 中文文档（极狐） | https://docs.gitlab.cn/docs/ | 中文文档站（官方文档仅 en-us / ja-jp） |
| GitLab 源码 | https://gitlab.com/gitlab-org/gitlab | 源码与 issue 讨论 |
| gitlab-runner 源码 | https://gitlab.com/gitlab-org/gitlab-runner | runner 配置（config.toml）与执行器说明 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（CI/CD 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | 选型说明：一体托管 + 流水线定义 + GitHub 归档 |
| 《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节 | 测试策略：CI 执行、缺陷上报、结果归档 |
| 《[开发部署规划](../../../规划/开发部署规划.md#server-gitlab)》4.5 节 | mjbk GitLab + runner + Renovate 部署实录 |
| 《[开发部署规划](../../../规划/开发部署规划.md#workflow)》7 节 | 开发工作流与 CI：分支模型、流水线、依赖升级 |
| 《[GitLab 部署使用说明](?../../开发服务器/GitLab部署使用说明.md》 | mjbk GitLab 安装配置内部文档 |
| 《[GitLab 迁移使用说明](?../../工具/GitLab迁移使用说明.md》 | 仓库迁移到 GitLab 的操作说明 |
| 《[Renovate 技术介绍](Renovate技术介绍.md)》 | 基于 GitLab 的依赖自动升级 |
| 《[Docker 与 Compose 技术介绍](Docker与Compose技术介绍.md)》 | runner 容器化运行的底座 |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | MR 流水线后端测试 job |
| 《[Allure 技术介绍](../工程化与质量/Allure技术介绍.md)》 | CI 产物：测试报告归档 |
| 《[Kiwi TCMS 技术介绍](../工程化与质量/KiwiTCMS技术介绍.md)》 | 用例库：缺陷链接指向 GitLab Issue |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19