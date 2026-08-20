# MinIO 技术介绍

> S3 兼容对象存储 · BMS 统一文件存储底座

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › MinIO 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**MinIO** 是一个用 Go 语言编写的**S3 兼容对象存储**服务，提供「桶 + 对象」的文件存取模型。
S3 是 Amazon 提出的对象存储协议标准，MinIO 完整兼容该协议，因此客户端、工具链都可以直接用 S3 生态的 SDK 对接，将来换云上 S3 服务也不需要改业务代码。
BMS 用它承载全部业务文件（附件、导入导出文件、图片/PDF 等），并支撑多实例共享文件。

- **定位**：BMS 唯一文件存储端点，backend 多副本共享同一存储，无本地磁盘依赖。
- **版本**：RELEASE 命名滚动发布（如 RELEASE.2026-xx），无大版本概念，跟随官方稳定线升级。
- **许可**：AGPL-3.0。仅作独立服务进程部署、不修改源码时无传染性；官方另提供商业订阅（见《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节许可分析）。
- **部署**：Docker Compose 独立容器，详见《[MinIO 部署使用说明](?../../开发服务器/MinIO部署使用说明.md》。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 桶（Bucket） | 对象的容器，类似数据库的库：BMS 按用途建桶（附件、导出、临时分片等），桶名全局唯一 |
| 对象（Object） | 存储的基本单位，由「桶 + key」定位；key 相当于路径，BMS 用业务前缀组织（如 `tenant/{id}/attach/xxx`） |
| S3 协议 | Amazon 定义的对象存储访问协议（HTTP + 签名鉴权），MinIO 兼容实现，SDK 与工具直接通用 |
| Access Key / Secret Key | 访问凭据，类似账号密码；BMS 通过 Secret 管理下发，不入库不写配置明文 |
| 预签名 URL | 带时效签名的访问链接：无需登录凭据，有效期内可直接上传/下载对象，BMS 用其实现「限时下载、图片直开预览」 |
| 分片上传（Multipart Upload） | 大对象拆成多个分片分别上传、最后合并；BMS 用 `.part` 后缀的临时对象标识未完成分片，全部传完合并为最终对象 |
| 孤儿分片 | 上传中断遗留的 `.part` 临时对象，由 Celery 定时任务扫描回收，避免存储泄漏 |
| ETag | 对象内容的校验标记，用于一致性校验与断点续传比对 |
| 纠删码（Erasure Coding） | MinIO 的默认数据冗余机制：数据分片分散到多块磁盘，坏盘时可自动恢复，是分布式部署的基础 |
| 生命周期（Lifecycle） | 按规则自动清理/迁移旧对象，BMS 可作为临时文件自动过期的兜底策略 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **统一文件存储**：附件、导入模板、导出结果、图片/PDF 等全部对象存储，backend 多实例共享同一端点，无状态横向扩展（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节）。
- **预签名 URL 限时下载**：下载/预览接口生成短时效预签名 URL（含权限校验），浏览器直连 MinIO 拉取，避免大文件经过后端转发。
- **大文件分片上传**：≤20MB 整包上传；超限分片 + 断点续传，分片用 `.part` 标识的临时对象存 MinIO，合并后清理，见《[项目规划说明](../../../规划/项目规划说明.md#modules)》第 5 节「文件管理」模块。
- **孤儿分片回收**：上传中断遗留的 `.part` 对象由 Celery 周期性任务扫描清理（见《[Celery 技术介绍](Celery技术介绍.md)》）。
- **本地开发模拟**：存储层做抽象接口，本地开发/测试可切文件系统实现，不强制起 MinIO；生产独立部署或对接现有 S3 服务。
- **AI 能力复用**：阶段十五 Milvus 向量库依赖的对象存储直接复用 MinIO。

```python
from datetime import timedelta
from minio import Minio

client = Minio("minio:9000", access_key="AKIA...", secret_key="...", secure=False)

url = client.get_presigned_url("GET", "bms-attach", "tenant/1/attach/a.pdf",
                               expires=timedelta(minutes=30))
```

## 4. 选型对比 <a id="compare"></a>

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| **MinIO（选中）** | S3 协议通用、自托管可控、Docker 一键部署、生态成熟（各语言 SDK） | AGPL-3.0（独立服务无传染）、需自行运维 | 私有化 + S3 兼容兼顾，可平滑换云上 S3 |
| 云上 S3 / OSS 等 | 免运维、容量无限 | 依赖外网供应商，信创/内网场景不适用 | 作为 MinIO 的对等替换保留，接口层已兼容 |
| Ceph RGW | 对象+块+文件一体 | 部署运维重，单为对象存储杀鸡用牛刀 | 复杂度超出项目需求 |
| SeaweedFS | 轻量快速 | 生态小、S3 兼容性弱 | 生态与兼容性不满足 |
| 共享磁盘（NFS） | 实现最简单 | 单点、无对象协议、无预签名能力 | 仅本地开发模拟用，生产不用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **AGPL 边界**：MinIO 以独立服务进程运行、不改源码即不传染；禁止为优化而修改 MinIO 源码内嵌项目（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节合规要求）。
- **凭据安全**：Access/Secret Key 走 Secret 管理下发，严禁硬编码进代码或提交仓库；定期轮换。
- **时钟同步**：S3 签名依赖时间戳，服务器时间偏差过大会导致签名校验失败，MinIO 与客户端机器都要配置 NTP。
- **预签名 URL 时效**：时限宁短勿长，下载接口每次按需签发；URL 不落入审计/日志明文，防止泄漏后被滥用。
- **分片残留**：上传中断会留下 `.part` 对象，靠 Celery 定时回收；清理任务要按创建时间阈值过滤，别误删正在上传的分片。
- **桶与 key 命名**：桶名全局唯一且创建后不能改名；key 用业务前缀组织（租户隔离），别用用户原始文件名直接当 key。
- **单机最小配置**：单机部署时纠删码需要至少 4 块磁盘或启用单盘模式，部署前读《[MinIO 部署使用说明](?../../开发服务器/MinIO部署使用说明.md》确认参数。
- **强一致性**：MinIO 对象读写是强一致的，无需自己维护缓存一致性；但列表操作分页与数量大时注意性能。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| MinIO 官网 | https://min.io/ | 产品介绍与下载 |
| MinIO 官方文档（Linux 版） | https://min.io/docs/minio/linux/index.html | 部署、运维、功能权威文档 |
| MinIO Python SDK 文档 | https://min.io/docs/minio/python/index.html | Python 客户端用法（put/get/presigned） |
| MinIO GitHub | https://github.com/minio/minio | 源码与 issue |
| MinIO 控制台文档 | https://min.io/docs/minio/linux/reference/minio-console/index.html | Web 控制台管理与排障 |
| S3 API 参考 | https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html | 协议标准参考（MinIO 兼容此 API） |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节 | 后端技术栈：对象存储条目 |
| 《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节 | 文件管理模块：分片上传、断点续传、预签名下载规则 |
| 《[MinIO 部署使用说明](?../../开发服务器/MinIO部署使用说明.md》 | 开发服务器上的部署步骤与排障 |
| 《[python-multipart 技术介绍](python-multipart技术介绍.md)》 | 上传入口的 multipart 解析 |
| 《[Celery 技术介绍](Celery技术介绍.md)》 | 孤儿分片回收、日志归档等任务 |
| 《[openpyxl 技术介绍](openpyxl技术介绍.md)》 | 导出文件写入后落 MinIO 分发 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19