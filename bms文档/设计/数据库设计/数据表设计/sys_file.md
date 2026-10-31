# sys_file（文件元数据表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_file

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | file 服务租户库 `bms_file_{code}` |
| 覆盖模块 | 14-文件管理 |
| 上游依据 | [需求 02-1](../../../项目/08_通用能力/需求/02_需求_文件与导入导出.md#r02-1)、《[概要设计 · 文件管理](../概要设计/13_概要设计_文件管理.md)》、《[架构设计 · 文件管理](../架构设计/20_架构设计_子系统_文件管理.md)》§2 / §3 |
| ORM 模型 | `bms_file/domains/file/models/file.py::SysFile`（继承 `BaseModel`） |
| 状态 | 已设计 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[14-数据库设计 · 文件管理](../14_数据库设计_文件管理.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。
本表承载「文件元数据 + 上传会话状态」，**内容存对象存储**（私有桶），库内只存 key 与校验值。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `name` | VARCHAR(255) | 否 | — | 原始文件名（含扩展名；列表展示与下载文件名） |
| `ext` | VARCHAR(32) | 是 | — | 小写扩展名（不含点；无扩展名为空）——白名单校验与列表筛选用 |
| `bucket` | VARCHAR(64) | 否 | 默认 `bms-files` | 对象存储桶名 |
| `object_key` | VARCHAR(512) | 否 | — | 对象 key（`{tenant_code}/files/{yyyy}/{mm}/{file_id}`；**秒传可与既有行相同，非唯一**） |
| `size` | BIGINT | 否 | > 0 | 文件字节数 |
| `mime_type` | VARCHAR(128) | 否 | — | **服务端嗅探**得到的 MIME（不采信客户端声明） |
| `sha256` | CHAR(64) | 否 | — | 整文件 SHA256（初始化时由客户端声明，完成时校验） |
| `uploader_id` | BIGINT | 是 | — | 上传人（雪花 ID；系统产物可空） |
| `source` | VARCHAR(16) | 否 | 默认 `upload` | 来源：`upload` / `dedup` / `print` / `export` |
| `status` | VARCHAR(16) | 否 | 默认 `uploading` | 状态：`uploading` / `completed` / `failed` / `orphan` |
| `upload_id` | VARCHAR(64) | 是 | 单列唯一 | 分片会话标识（整包上传为空；与 `sys_file_part` 关联的业务键） |
| `total_parts` | INT | 是 | — | 分片总数（整包为空；≤ 10000） |
| `uploaded_parts` | INT | 是 | 默认 0 | 已上传片数（冗余计数，供列表与巡检） |
| `part_size` | INT | 是 | — | 本次会话分片大小（字节；断点续传续会话用） |
| `expires_at` | DATETIME | 是 | — | 会话过期时刻（UTC）；`uploading` 的**孤儿判定权威字段** |
| `completed_at` | DATETIME | 是 | — | 完成时刻（UTC） |
| `remark` | VARCHAR(256) | 是 | — | 失败原因 / 备注 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删；删除不动物体、不释放配额） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_file_upload_id` | 唯一 | `(upload_id)` | 分片会话标识唯一（**单列**：NULL 可多行，整包上传不受限） |
| `idx_sys_file_uploader_created_at` | 普通 | `(uploader_id, created_at)` | 列表主路径（按上传人筛选 + 时间排序） |
| `idx_sys_file_status_expires_at` | 普通 | `(status, expires_at)` | 孤儿回收扫描唯一热路径（`uploading` + 超期） |
| `idx_sys_file_sha256_size` | 普通 | `(sha256, size)` | 秒传判定 + 共享对象引用计数（同 `sha256`+`size` 即同一对象） |

- 无物理外键（`uploader_id` 逻辑指向用户表）。
- 业务索引 4 个（公共 `idx_sys_file_deleted_at` 由基类元数据约定生成，按总览口径不在此重复列）。
- **`object_key` 不单建索引**：秒传要求同 `sha256` + `size`，共享对象的引用计数走 `idx_sys_file_sha256_size`，无需按 key 反查。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（元数据行量级小；大文件内容在对象存储）。
- **归档**：不归档（随租户库备份）；对象内容由对象存储生命周期策略承载，不进入数据库归档流转。
- **状态口径**：`status` 为唯一状态真值；`completed` 才可下载 / 预览；`deleted_at` 非空即为回收站态（对象仍在）。
- **建表**：已定稿并进入 file 服务的**租户链**，由启动期建表引导 / `ops.init_schema` 幂等建表落地（`sys_table_ownership.status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-31 | v1 | 新建（03_01 文件管理）：元数据 + 上传会话 + 四态状态机；秒传共享 `object_key` 语义 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套
