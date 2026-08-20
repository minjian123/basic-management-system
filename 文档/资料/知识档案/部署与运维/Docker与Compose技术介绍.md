# Docker 与 Compose 技术介绍

> 容器引擎 + 编排工具 · BMS 开发与生产环境的统一底座

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › Docker 与 Compose 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Docker Engine** 是开源容器引擎，负责镜像构建、容器运行、卷与网络管理，
是「镜像 → 容器」这套玩法的工业标准实现。
**Docker Compose** 是配套的多容器编排工具：用一个 YAML 文件声明全部服务
（backend、redis、数据库等），一条命令 `docker compose up -d` 全部拉起。

- **定位**：BMS 的容器化底座，保证开发与生产环境一致（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）。
- **版本**：Engine 为 2x.x 系列（持续更新，装最新稳定版即可）；Compose v2 用 Go 重写，已内置到 `docker compose` 命令行。
- **许可**：Apache-2.0，免费开源、无商用订阅（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：mjbk 为 Ubuntu 24.04.4，apt 清华 docker-ce 源直装；本地开发机用 Windows 容器方案，命令与行为与 Linux 一致。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 镜像（Image） | 只读的运行环境模板，按层组织，可推送到 Registry 分发 |
| 容器（Container） | 镜像的运行实例：独立进程空间，本质是受隔离的进程 |
| 分层（Layer） | Dockerfile 每条指令生成一层，层可共享可缓存，构建与分发都快 |
| 卷（Volume） | 数据持久化机制；命名卷由 Docker 统一管理，删容器不丢数据 |
| 网络（Network） | 容器间默认走 bridge 网络，服务名即主机名，互相解析通信 |
| Compose 文件 | YAML 声明 services / networks / volumes，是「一键编排」的蓝图 |
| docker compose up / down | 按依赖顺序拉起 / 停止全部服务，开发、CI、生产共用同一套文件 |
| healthcheck | 容器健康探针，编排与监控据此判断服务是否真正就绪 |
| docker.sock | Docker 守护进程的套接字；挂载它等于给容器 root 权限，gitlab-runner 借此在容器内再跑容器 |
| data-root | Docker 数据目录（镜像 / 容器 / 卷）；mjbk 已迁到 NVMe SSD（`/mnt/ssd2t/docker`） |
| .env 文件 | Compose 变量替换的来源，装密码与密钥，必须 gitignore 不入库 |
| 镜像加速 | 拉取慢时配国内镜像源；项目约定下载类操作优先国内镜像，不长时间等待默认源 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **一键编排**：backend（多副本）+ celery-worker + celery-beat + event-worker + frontend（nginx）+ redis + rocketmq（nameserver + broker）+ elasticsearch + minio + 数据库 + 监控全家桶，全部由 Compose 拉起（《[项目规划说明](../../../规划/项目规划说明.md#deploy-compose)》19.3 节）。
- **开发生产一致**：本地与 mjbk 共用同一套 Compose 编排文件；开发期依赖（Redis / RocketMQ / ES / MinIO）本地不装原生服务，统一容器提供（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **gitlab-runner 容器化**：runner 以容器方式运行，挂载 docker.sock、executor=docker，开发环境并发上限 2（见《[GitLab 技术介绍](GitLab技术介绍.md)》）。
- **阶段十五 AI**：Milvus（含 etcd，MinIO 复用）随 AI 阶段一并加入 Compose（见《[Milvus 技术介绍](../后端核心/Milvus技术介绍.md)》《[etcd 技术介绍](etcd技术介绍.md)》）。
- **安装方式**：mjbk 为 Ubuntu 24.04.4，apt 清华 docker-ce 源直装 Docker Engine，systemd 开机自启（见《[DockerEngine 部署使用说明](?../../开发服务器/DockerEngine部署使用说明.md》）。
- **数据落盘**：IO 敏感数据（数据库 / ES / MinIO / 镜像）走 NVMe SSD 命名卷，备份与读多写少数据走 HDD（《[开发部署规划](../../../规划/开发部署规划.md#server-disk)》4.2 节）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Docker Engine + Compose（选中）** | 优点：工业标准、生态最全、Compose 一键编排、团队上手成本低；缺点：守护进程单点（mjbk 常开，可接受） | 开发 / CI / 生产全链路统一，MVP 阶段最优解 |
| Podman | 优点：无守护进程、兼容 docker 命令；缺点：生态与工具链略弱，Compose 支持靠 podman-compose 拼装 | 备选，本项目无特殊诉求不引入 |
| containerd + nerdctl | 优点：更底层更精简；缺点：需自行拼装编排与工具链，学习成本高 | 不适合团队当前规模 |
| Kubernetes | 优点：编排能力强、自愈与扩缩；缺点：组件多、运维重，MVP 规模用不上 | 《项目规划说明》24 节明确 MVP 用 Compose，规模增长后按演进路线再迁移 |
| Rancher Desktop（Windows/WSL2） | 优点：Windows 本地友好；缺点：mjbk 已换装 Ubuntu，生产侧不适用 | 仅本地开发机备选，不作为项目方案 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **数据丢失**：匿名卷随容器删除而消失，持久化数据一律用命名卷并纳入备份范围。
- **docker.sock 等于 root**：拿到它的容器可控制宿主机 Docker，只暴露给 runner 这类可信容器。
- **拉镜像慢**：默认源访问不畅时立即切国内镜像源，不长时间等待（项目网络约定）。
- **时区与语言**：容器默认 UTC，涉及时间展示的服务记得设 `TZ` 环境变量。
- **内存预算**：mjbk 32GB 要同时承载 GitLab、全家桶与桌面，各服务按需设内存上限，部署后按实际占用调优。
- **.env 不入库**：密码与密钥只走 .env / 环境变量，gitignore 兜底，严禁提交。
- **Windows 与 Linux 差异**：本地开发机（Windows）与 mjbk（Linux）路径分隔符、换行符、权限模型不同，Dockerfile 与脚本按 Linux 口径写。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Docker 官方文档 | https://docs.docker.com/ | 权威文档，Engine / Compose / 网络 / 卷全覆盖 |
| Compose 文档 | https://docs.docker.com/compose/ | Compose 文件语法与多环境用法 |
| Compose 规范 | https://github.com/compose-spec/compose-spec | Compose 开放规范（跨工具通用） |
| Docker Hub | https://hub.docker.com/ | 官方镜像仓库，查镜像标签与 digest |
| Docker Engine 源码（moby） | https://github.com/moby/moby | Engine 源码与 issue 讨论 |
| 清华 docker-ce 镜像 | https://mirrors.tuna.tsinghua.edu.cn/docker-ce/ | mjbk apt 安装所用国内源 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（Docker 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | 选型说明：开发生产一致、一键编排 |
| 《[项目规划说明](../../../规划/项目规划说明.md#deploy-compose)》19.3 节 | 基础设施编排：初版 Compose 服务清单 |
| 《[开发部署规划](../../../规划/开发部署规划.md#server-base)》4.1 节 | mjbk 基础环境：清华 docker-ce 源安装实录 |
| 《[DockerEngine 部署使用说明](?../../开发服务器/DockerEngine部署使用说明.md》 | mjbk Docker 安装与配置内部文档 |
| 《[GitLab 技术介绍](GitLab技术介绍.md)》 | gitlab-runner 以容器方式运行（docker.sock、executor=docker） |
| 《[nginx 技术介绍](nginx技术介绍.md)》 | frontend 容器：静态托管与反向代理 |
| 《[MinIO 技术介绍](../后端核心/MinIO技术介绍.md)》 | 被编排的对象存储服务 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19