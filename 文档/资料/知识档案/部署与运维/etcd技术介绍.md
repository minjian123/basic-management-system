# etcd 技术介绍

> 分布式键值存储 · Milvus 元数据与集群协调

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › etcd 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**etcd** 是用 Go 编写的分布式**可靠键值存储**，
基于 **Raft 共识**算法保证强一致：写入多数节点确认后才算成功，
读到的数据保证是已提交版本。它诞生于 CoreOS，现为 CNCF 毕业项目，
是 Kubernetes 的「大脑」，也是众多分布式系统做协调与元数据存储的标准件。

- **定位**：BMS 阶段十五 AI 能力的配套组件——Milvus 向量库的元数据与集群协调依赖（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）。
- **版本**：3.5 / 3.6 系列（3.5 为长期维护线，3.6 为新版）。
- **许可**：Apache-2.0，免费开源（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：随 Milvus 于阶段十五加入 Compose 编排，MinIO 复用（《[开发部署规划](../../../规划/开发部署规划.md#server-services)》4.3 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| Raft 共识 | 选举 leader + 日志复制：写入先落多数节点再返回，保证强一致与故障可恢复 |
| key-value | 基本数据模型：扁平的键值对，值上限默认 4MB，适合元数据不适合大对象 |
| range | 按键前缀 / 区间批量读取，如取某 collection 下全部元数据 |
| watch | 订阅键的变更事件，节点间「谁上线了 / 配置变了」的实时感知靠它 |
| lease / TTL | 租约：键可绑定存活时间，节点心跳续租，掉线自动过期——分布式锁与成员发现的基础 |
| quorum | 法定多数：3 节点容忍 1 台故障、5 节点容忍 2 台，节点数必须为奇数 |
| MVCC | 多版本并发控制：每次写入生成新版本，读可按版本回看 |
| compact / defrag | 压缩旧版本、整理碎片，长期运行需定期执行防膨胀 |
| etcdctl | 官方命令行客户端，运维查键、看集群状态（`etcdctl endpoint status`）的第一工具 |
| 客户端库 | Go / Java / Python 等官方客户端，Milvus 等系统经它读写元数据 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **Milvus 依赖**：Milvus 用 etcd 存元数据（collection / 分区 / 索引信息）并做集群协调（节点发现、选主），是 Milvus 的标准组件（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节「Milvus（milvus + etcd，MinIO 复用）」）。
- **阶段十五随 AI 落地**：etcd 与 Milvus 一并加入 Compose 编排，MinIO 对象存储复用现有实例（《[开发部署规划](../../../规划/开发部署规划.md#server-services)》4.3 节）。
- **数据落盘**：etcd 对磁盘 fsync 延迟敏感，数据放 NVMe SSD 命名卷（《[开发部署规划](../../../规划/开发部署规划.md#server-disk)》4.2 节）。
- **边界说明**：BMS 业务代码不直接依赖 etcd，它只服务 Milvus 内部协调，运维上「了解即可」（《[技术栈知识档案总览](../技术栈知识档案总览.md#path)》学习路径）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **etcd（选中）** | 优点：CNCF 标准、Raft 强一致、API 简单、Go 客户端轻；缺点：值有大小上限，不适合存大对象 | Milvus 官方要求，云原生协调事实标准 |
| ZooKeeper | 优点：老牌、Hadoop 生态绑定深；缺点：Java 栈、API 风格较旧、社区重心已转移 | 新项目无历史包袱时不如 etcd |
| Consul | 优点：KV + 服务发现 + 健康检查一体、多数据中心强；缺点：组件面宽、BMS 只用 KV 属功能过剩 | 需要服务发现时再考虑 |
| Redis | 优点：快、团队已用；缺点：非共识协议、持久化语义弱，不适合承担强一致协调 | 缓存场景用 Redis，协调场景用 etcd，各司其职 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **节点数取奇数**：3 或 5，偶数没有额外容错收益反而浪费资源。
- **磁盘是命门**：Raft 每次提交都要 fsync，慢盘会让整个集群「变慢」，务必放 SSD。
- **别当缓存用**：etcd 为协调 / 元数据设计，高频读写大对象会拖垮集群；BMS 缓存走 Redis。
- **定期 compact + defrag**：MVCC 旧版本会堆积，长期运行需计划性清理。
- **客户端超时与重试**：网络抖动时客户端要配合理超时，避免雪崩式重试。
- **Windows 与 Linux 差异**：etcd 官方支持 Linux（生产容器）；Windows 本地体验请用 Docker 跑，别装 Windows 构建版。
- **备份**：etcd 数据 = Milvus 的「户籍档案」，纳入 mjbk 每日备份范围（《[开发部署规划](../../../规划/开发部署规划.md#backup)》8 节）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| etcd 官网 | https://etcd.io/ | 项目入口、下载、特性说明 |
| etcd 官方文档 | https://etcd.io/docs/ | 安装、运维、API 完整参考 |
| etcd 源码 | https://github.com/etcd-io/etcd | 源码与 issue 讨论 |
| Raft 论文 | https://raft.github.io/ | 共识算法原始论文（In Search of an Understandable Consensus Algorithm） |
| Raft 可视化讲解 | https://thesecretlivesofdata.com/raft/ | 动画演示选举与日志复制，入门 Raft 首选 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（Milvus + etcd 条目） |
| 《[Milvus 技术介绍](../后端核心/Milvus技术介绍.md)》 | etcd 的直接服务对象：向量库元数据与协调 |
| 《[MinIO 技术介绍](../后端核心/MinIO技术介绍.md)》 | Milvus 复用的对象存储（存向量数据本体） |
| 《[开发部署规划](../../../规划/开发部署规划.md#server-services)》4.3 节 | mjbk 基础设施：milvus / etcd 镜像与端口规划 |
| 《[Docker 与 Compose 技术介绍](Docker与Compose技术介绍.md)》 | etcd 的编排与数据落盘方式 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19