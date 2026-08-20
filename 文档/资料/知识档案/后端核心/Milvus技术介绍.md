# Milvus 技术介绍

> 分布式向量数据库 · BMS 语义检索底座

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › Milvus 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Milvus** 是一个开源的**向量数据库**：专门存储「向量」（文本、图片的数学表示），
并按相似度快速检索「意思相近」的内容。全文检索（ElasticSearch）解决「关键词匹配」，
向量检索解决「语义相近」——比如搜「采购审批流程」能命中标题写着「请购单签批办法」的文档，
这正是阶段十五「语义搜索与文件问答」需要的能力。

- **定位**：BMS 阶段十五 AI 能力的向量存储底座，承载文件内容分段向量与知识库向量。
- **版本**：项目部署规划基于 2.x 稳定线（依赖 etcd + MinIO 的组合为 2.x 架构）；截至 2026.8 官方最新为 3.0.0（2026.7 发布），升级另行评估。
- **许可**：Apache-2.0，OSI 认证开源，无合规顾虑。
- **依赖**：etcd（存元数据）+ MinIO（存向量数据文件，BMS 复用现有 MinIO）。
- **客户端**：pymilvus（官方 Python SDK）。
- **部署**：Docker Compose 独立容器（milvus + etcd），端口 19530（gRPC），仅内网，阶段十五随 AI 能力引入。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 向量（Vector） | 一串数字，表示一段文本/图片的语义；两段内容意思越接近，向量距离越近 |
| Embedding | 用 embedding 模型把文本转成向量的过程，是向量检索的前提；BMS 的 embedding 管线经 RocketMQ 事件驱动 |
| Collection | 向量「表」：一批同结构向量的集合；BMS 按租户建（`bms-{tenant}-doc`、`bms-{tenant}-embedding`） |
| 向量索引 | 加速相似度检索的数据结构（如 IVF、HNSW 系列）：用内存换速度，数据量大时必建 |
| 相似度度量 | 衡量向量远近的方法：余弦（cosine）、欧氏距离（L2）、内积（IP）等，建集合时选定 |
| 标量字段 | 向量之外的普通字段（如 `file_id`、`chunk_no`、`tenant_id`），用于过滤与回查定位 |
| etcd | 分布式键值存储，Milvus 用它保存集群元数据（集合定义、分片分布）；etcd 数据丢失 = 元数据丢失 |
| MinIO（对象存储） | Milvus 把向量数据文件落在对象存储上；BMS 直接复用现有 MinIO，不新增存储组件 |
| Standalone 模式 | 单进程部署形态（组件全在一个容器组里），BMS 的部署方式；更大规模才用 Cluster 模式 |
| 混合检索 | 向量 + 标量/关键词（BM25）混合查询，2.4+ 支持；可让「语义相近」和「关键词精确」一起参与排序 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **语义搜索与文件问答**（阶段十五，八项 AI 能力之一）：文件内容分段后，分段文本落库（`ai_file_segment` 表：`file_id`、`chunk_no`、`content`、`vector_id`），向量存 Milvus；检索时先取 top-k 相似分段，再交给 LLM 生成答案（RAG，见《[LLM 适配层技术介绍](LLM适配层技术介绍.md)》）。
- **租户隔离**：collection 按租户命名（`bms-{tenant}-doc` 等，见《[命名规范](../../../规范/命名规范.html)》第 10 节），查询强制携带租户过滤，向量库按租户边界隔离（规划 3.1 节设计约束）。
- **embedding 管线事件驱动**：文件新增/变更事件经 RocketMQ 投递，event-worker 消费后做分段、向量化、入库（复用现有事件模型，见《[RocketMQ 技术介绍](RocketMQ技术介绍.md)》）。
- **独立部署**：milvus + etcd 容器组，MinIO 复用（《[开发部署规划](../../../规划/开发部署规划.html)》第五批，阶段十五引入）；端口 19530 仅内网。
- **与全文检索分工**：关键词精确匹配走 ElasticSearch，语义相近走 Milvus，两者互补不替代（见《[ElasticSearch 技术介绍](ElasticSearch技术介绍.md)》）。

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://127.0.0.1:19530")

# query_vector：查询文本经 embedding 模型转成的向量
res = client.search(
    collection_name="bms-t001-doc",
    data=[query_vector],
    limit=5,
    output_fields=["file_id", "chunk_no"],
)
for hit in res[0]:
    print(hit["entity"]["file_id"], hit["entity"]["chunk_no"])
# 拿 file_id + chunk_no 回查 ai_file_segment 取原文，再交给 LLM 生成答案
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| **Milvus（选中）** | 专用向量数据库、Apache-2.0、索引类型丰富、支持混合检索、多租户场景成熟 | 依赖 etcd + MinIO，组件比「单库方案」多 | 语义检索 + 租户隔离 + 复用现有 MinIO，最贴合 |
| pgvector（PostgreSQL 扩展） | 不新增组件、事务一致 | 向量规模大时性能受限；与业务主库混跑互相影响 | 小规模实验可用，生产不采用 |
| Qdrant | 易用、Rust 实现、单二进制部署 | 中文资料与生态少于 Milvus | 合格备选，不采用 |
| ElasticSearch dense_vector | 复用现有 ES | 向量检索非 ES 主业，索引类型与性能有限；与全文检索混跑抢资源 | 不采用，语义检索交给专用向量库 |
| FAISS（内存检索库） | 检索快、灵活 | 只是库不是服务：无持久化、无多租户管理，要自建一整套 | 不采用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **依赖链顺序**：MinIO/etcd 必须先于 Milvus 就绪；etcd 存元数据，备份时 etcd 与 MinIO 都要覆盖（规划 19.4 节）。
- **内存规划**：向量索引要加载进内存，内存需求 ≈ 向量条数 × 维度 × 4 字节再乘索引系数；上线前按预估数据量算一遍，别低估。
- **租户隔离靠 collection**：一租户一 collection，查询代码强制带租户过滤；不要所有租户混一个 collection 再靠字段过滤，隔离强度弱。
- **向量与文本要同步删**：分段文本在 `ai_file_segment`、向量在 Milvus，文件删除/变更时两边必须同步清理（走事件驱动），否则出现「幽灵向量」——搜出来指向已删内容。
- **索引类型别乱选**：HNSW 召回好但吃内存，IVF 系列省内存但召回略低；按数据量与内存预算选，建后做召回率验证。
- **版本升级谨慎**：2.x 与 3.x 架构差异大（3.0 引入湖仓架构），升级必须走官方迁移文档并全量回归；项目当前基于 2.x 稳定线。
- **检索结果要回查**：Milvus 返回的是 `file_id`/`chunk_no` 等定位字段，原文回查数据库，保证展示内容与库内一致。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Milvus 官网 | https://milvus.io/ | 产品入口与下载 |
| Milvus 官方文档 | https://milvus.io/docs/ | 概念、部署、用法权威文档 |
| Milvus GitHub | https://github.com/milvus-io/milvus | 源码与版本发布记录 |
| pymilvus（Python SDK） | https://github.com/milvus-io/pymilvus | 本项目使用的 Python 客户端 |
| etcd 官网 | https://etcd.io/ | Milvus 元数据依赖组件 |
| Zilliz（Milvus 商业云） | https://zilliz.com/ | 厂商托管服务，了解托管形态时参考 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-backend)》2.1 节 | 后端技术栈：AI（阶段十五）条目 |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节 | 向量检索选型与租户隔离约束 |
| 《[项目规划说明](../../../规划/项目规划说明.html#tables)》6 节 | `ai_file_segment` 表：分段文本落库、向量存 Milvus |
| 《[项目规划说明](../../../规划/项目规划说明.html#env)》17 节 | Milvus（含 etcd）随阶段十五加入 Compose |
| 《[命名规范](../../../规范/命名规范.html)》第 10 节 | Milvus collection 命名 `bms-{租户}-{用途}` |
| 《[LLM 适配层技术介绍](LLM适配层技术介绍.md)》 | RAG：向量检索结果交给 LLM 生成答案 |
| 《[MinIO 技术介绍](MinIO技术介绍.md)》 | Milvus 向量数据的对象存储（复用） |
| 《[RocketMQ 技术介绍](RocketMQ技术介绍.md)》 | embedding 管线事件驱动 |
| 《[etcd 技术介绍](../部署与运维/etcd技术介绍.md)》 | Milvus 元数据依赖组件 |
| 《[开发部署规划](../../../规划/开发部署规划.html)》 | 第五批部署（milvus + etcd）、端口 19530 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19