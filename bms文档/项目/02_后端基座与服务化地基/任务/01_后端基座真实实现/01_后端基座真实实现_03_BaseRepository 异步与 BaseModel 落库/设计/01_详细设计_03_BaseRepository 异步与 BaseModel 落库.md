# BaseRepository 异步与 BaseModel 落库详细设计

> 后端基座与服务化地基 · 01 后端基座真实实现 · 03 BaseRepository 异步与 BaseModel 落库 · 详细设计

[文档首页](../../../../../../文档首页.md) › [03 BaseRepository 异步与 BaseModel 落库](../01_后端基座真实实现_03_BaseRepository 异步与 BaseModel 落库.md) › 01 详细设计　|　[父任务：后端基座真实实现](../../01_后端基座真实实现.md) · [本阶段需求](../../../../需求/01_需求_后端基座真实实现.md) · [排期计划](../../../../计划/01_计划_后端基座与服务化地基.md)

## 1. 概述 <a id="overview"></a>

- **目标**：把阶段一交付的 `BaseDbRepository` 占位填为**真实异步数据库实现**——会话构造注入、CRUD（含软删除 / 硬删出口）、作用域条件（软删除 + 数据范围 + 租户）翻译为 SQL WHERE、基础 ORDER BY 与分页（LIMIT/OFFSET）、乐观锁冲突转译、写入字段严格白名单与租户写入口径；同步验证 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）在异步会话下真实生效，落四库类型映射与软删除复合唯一索引口径，落 `sys_module` 表与平台域种子，并补齐 01_01 遗留的统一会话入口（`session_scope`）与索引命名规范修正。
- **依据**：《架构设计 · 后端基础类体系》「各层基类与模块约定」「阶段交付与跨阶段基座契约」节；《架构设计 · 数据访问与分片》「多数据源管理」「读写分离」「事务边界规则」「查询规范」节；《架构设计 · 数据架构》「数据规范」「回收站机制」节；《后端基类清单》「模块基类（数据访问 / 服务 / 契约 / 模型）」「数据访问与多租户基座」节；《后端开发规范》「后端基座体系（强制）」「SQL 与数据访问规范」「异步与并发」节；《数据库开发规范》《命名规范》；需求 [01-3](../../../../需求/01_需求_后端基座真实实现.md#r01-3)。
- **范围（本任务）**：
  1. `BaseDbRepository` 真实实现：构造注入 `AsyncSession`、`model` 类属性、CRUD / `exists` / `list_page` / `list_cursor`（偏移口径）、作用域条件 → WHERE 翻译、基础 ORDER BY（默认 `id` 升序）、写入字段严格白名单、租户 `create` 注入与 `update` 禁改、乐观锁经 `flush()` 触发并在 `_guard_version` 转 409、`delete` 默认软删除 + `soft_delete` / `hard_delete` 显式出口。
  2. `BaseModel` 落库验证：异步会话下雪花 ID、审计事件自动填充、软删除、乐观锁真实生效；字段与事件实现不变（阶段一已交付），本任务补异步会话用例。
  3. 四库类型映射（含布尔 / 多值字段口径）与软删除复合唯一索引 `(唯一字段, deleted_at)` 口径验证：离线编译四方言 DDL 断言 + SQLite 真库验证多 NULL 共存；真库实测归 01_05。
  4. `sys_module` 表与平台域种子落库（`ops/seed_module.py`，幂等，复用 `PLATFORM_MODULES` 单一来源）。
  5. 统一会话入口 `session_scope`（按租户上下文 / 库键 + 读写角色 + 会话工厂），并把 dict / listing 既有 6 处重复 `_session` 迁入（01_01 遗留「会话入口统一归任务 03」）。
  6. 索引命名规范修正：`Base.metadata` 设 `ix` 命名模板，`index=True` 生成的索引名由 `ix_*` 对齐规范 `idx_{表}_{列}`。
- **不含（明确归口，见第 8 节）**：排序契约 DB 侧细化（四库 NULLS 口径、排序字段索引配合、分页限深 100 页、keyset 游标键）、Alembic 在线迁移与 SQLite 全量自动建表、`ops` 批量迁移（01_04）；三库真库集成、CI `verify/db` 档、达梦方言实测（01_05）；`sys_module` 升格服务目录与接库唯一性校验（03_01 / 03_02）；RBAC 数据范围规则真实注入与写校验（RBAC 阶段）；dict / listing 写路径语义与其仓储化（本任务只改会话入口）。

## 2. 现状与差距 <a id="gap"></a>

| 关注点 | 现状（阶段一 / 01_01 / 01_02 交付） | 差距（本任务目标） |
| --- | --- | --- |
| `BaseDbRepository` | 继承 `BaseScopedRepository` + `BaseStub`，CRUD 全部抛 `NotImplementedError`，不连库 | 真实异步 CRUD / 分页 / 存在性 / 软删除 SQL / 乐观锁转译；退出 `BaseStub` |
| 会话接入 | 仓储无会话入口；请求级会话依赖 `get_db` / `get_write_db` 已就绪 | 构造注入 `AsyncSession`，与服务事务同会话 |
| 作用域条件 | `_scope_conditions()` 产出 `ScopeCondition` 列表（软删除 → 数据范围 → 租户），仅内存基线按它过滤 | 统一翻译为 SQL WHERE（11 种操作符） |
| 排序 / 分页 | `_apply_sort` 占位原样返回；`list_page` / `list_cursor` 走基类 `list()` 切片 | 基础 ORDER BY（模型列解析）+ `list_page` LIMIT/OFFSET + `list_cursor` 偏移口径 |
| 写入口径 | 内存基线 `create` / `update` 直接落字段，无白名单与租户写入口径 | 严格白名单（拒绝 `id` / 审计 / `version` / `deleted_at`）；`tenant_scoped` 的 create 注入 / update 禁改 |
| 删除 | 内存基线硬删；DB 侧无实现 | `delete` 默认软删除（`soft_delete_enabled=True`）、`soft_delete` / `hard_delete` 显式出口 |
| `BaseModel` | 字段 / 审计事件 / `version_id_col` / `soft_delete` 已交付（Kiwi 30，同步会话验证） | 异步会话下真实生效验证（仓储 flush 链路） |
| 四库类型映射 | `models/base.py` 文档映射表与实测不符（PostgreSQL 布尔实为 `BOOLEAN`；无多值字段口径） | 离线编译四方言 DDL 断言类型与复合唯一；回写映射表 |
| 索引命名 | `index=True` 生成 `ix_*`（`ix_sys_module_deleted_at`），规范要求 `idx_*` | `Base.metadata` 命名模板全局对齐 `idx_{表}_{列}` |
| `sys_module` | 模型已声明（`models/platform.py`），无建表与种子；`ModuleRegistry` 为内存固定清单 | `ops/seed_module.py` 幂等建表 + 平台域 sys/wf/rpt/ai 种子 |
| 会话入口 | dict / listing 共 6 处重复 `_session`（各自 `async_sessionmaker`） | 统一 `session_scope` 入口并迁移 |
| 测试 | DB 骨架断言为「一律抛错」；无四方言 DDL 与 `sys_module` 种子用例 | 真实 DB 仓储用例 + 四方言 DDL 用例 + 种子用例 + 会话入口用例 |

## 3. 交付物清单 <a id="tree"></a>

```text
backend/
├── app/
│   ├── models/
│   │   └── base.py                                # 修改：ix 命名模板（idx_*）+ 四库类型映射表回写（布尔 / 多值）
│   ├── db/
│   │   └── session.py                             # 修改：新增 session_scope 统一会话入口
│   ├── repositories/
│   │   ├── base_scoped_repository.py              # 修改：soft_delete / hard_delete 派生默认（DB 覆写）
│   │   └── base_db_repository.py                  # 修改：真实实现（会话注入 / 作用域 SQL / CRUD / 分页排序 / 白名单 / 乐观锁）
│   ├── dict/
│   │   ├── providers.py                           # 修改：_session 迁 session_scope
│   │   ├── query.py                               # 修改：_session 迁 session_scope
│   │   ├── service.py                             # 修改：_session 迁 session_scope
│   │   └── sql.py                                 # 修改：_session ×2 迁 session_scope
│   └── listing/
│       └── store.py                               # 修改：_session 迁 session_scope
├── ops/
│   └── seed_module.py                             # 新增：sys_module 幂等建表 + 平台域种子
└── tests/
    ├── repositories/
    │   ├── test_db_repository.py                  # 新增：DB 仓储真实用例（CRUD / 作用域 / 软删 / 租户 / 乐观锁 / 分页排序 / 白名单）
    │   └── test_base_repository.py                # 修改：DB 骨架占位断言改真实语义；`_apply_sort` 断言适配
    ├── models/
    │   └── test_type_mapping.py                   # 新增：四方言 DDL 类型与复合唯一 / 索引命名 / SQLite NULL 唯一语义
    ├── db/
    │   └── test_session_scope.py                  # 新增：统一会话入口（库键 / 读写角色 / 自定义工厂）
    └── ops/
        └── test_module_ops.py                     # 新增：seed_module 幂等与 dry-run

bms文档/
├── 后端基类清单.md                                 # 修改：§2 / §5 / §8 / §10 状态、继承链与 session_scope 回写
├── 规范/后端开发规范.md                            # 修改：「SQL 与数据访问规范」仓储写入与软删 / 硬删口径补充
├── 设计/架构设计/07_架构设计_数据架构.md            # 修改：「数据规范」布尔 / 多值字段存储口径回写
└── 设计/数据库设计/数据表设计/sys_module.md         # 修改：状态与落库注记（种子先行、迁移归 01_04）
```

## 4. 领域设计 <a id="design"></a>

### 4.1 `BaseDbRepository` 结构与依赖 <a id="structure"></a>

`app/repositories/base_db_repository.py` 由占位骨架改为真实实现：

| 成员 | 说明 |
| --- | --- |
| `model: ClassVar[type[ModelT]]` | 子类声明所操作的 ORM 模型（类型参数上界 `ModelT: BaseModel`）；列解析与实体构造的唯一依据 |
| `__init__(session: AsyncSession)` | 构造注入请求级会话（`Depends(get_db)` / `get_write_db` / `get_uow` 的同一会话）；仓储不提交、不开关会话，事务边界归服务层工作单元 |
| `_column(field) -> InstrumentedAttribute[Any]` | 字段名 → 模型列对象；非映射列（不存在 / 关系属性 / 普通属性）抛 `ConfigError` 快速失败 |
| `_scope_where() -> list[ColumnElement[bool]]` | `_scope_conditions()` 逐条翻译为 SQL 条件（次序软删除 → 数据范围 → 租户不变） |
| `_select() -> Select[tuple[ModelT]]` | `select(model).where(*scope)` 基础语句 |
| `_write_values(values, *, creating) -> dict[str, object]` | 写入字段白名单与租户写入口径（见 4.3） |

- 继承链调整：去掉 `BaseStub`（不再是未实现桩），保留 `BaseScopedRepository → BaseRepository → BaseObject`；同一变更同步《后端基类清单》§2 / §5 / §10。
- `_apply_sort` 覆写保持契约层泛型签名（内部 `isinstance(statement, Select)` 判定后拼 ORDER BY，返回原语句类型），避免基类签名收窄造成的类型不兼容。
- 仓储不感知引擎 / 租户库选择：会话由依赖按请求租户与读写角色选引擎（01_01 / 01_02 已交付）；`_resolve_binding` / `_resolve_shard` 钩子语义不变。

### 4.2 作用域条件 → SQL WHERE 翻译 <a id="scope-sql"></a>

`ScopeCondition(field, operator, value)` 的 11 种操作符统一映射（与内存基线 `_match` 语义对齐）：

| 操作符 | SQL 翻译 | 备注 |
| --- | --- | --- |
| `eq` / `ne` | `col == value` / `col != value` | — |
| `in` | `col.in_(values)` | 空序列翻译为恒假（与内存 `any(...)` 一致）；非序列抛 `ConfigError` |
| `like` | `col.contains(value, autoescape=True)` | 子串匹配（等价内存 `target in value`）；`%` / `_` 自动转义；非字符串抛 `ConfigError` |
| `gt` / `gte` / `lt` / `lte` | 对应比较运算 | — |
| `between` | `col.between(low, high)` | 值须为二元序列，否则 `ConfigError` |
| `is_null` / `is_not_null` | `col.is_(None)` / `col.is_not(None)` | 忽略 value |

- **失败快速**（决策 11）：条件字段不在模型映射列、操作符不在 `SCOPE_OPERATORS`、值形态非法，一律抛 `ConfigError`，杜绝静默丢条件造成的越权可见。
- 翻译结果仅由字段名解析（模型列对象）与绑定参数构成，**不拼接用户输入**（排序同口径）。

### 4.3 CRUD 语义与写入口径 <a id="crud"></a>

| 方法 | 语义 |
| --- | --- |
| `list(*, sort)` | `SELECT` 全列（禁 `SELECT *` 由 ORM 列清单保证）+ 作用域 WHERE + ORDER BY；无 `sort` 默认 `id ASC` |
| `get(item_id)` | 按 ID + 作用域条件查询；不存在 / 已软删 / 不在数据范围返回 `None` |
| `count()` | `SELECT COUNT(*)` + 作用域 WHERE |
| `exists(item_id)` | 覆写为 `SELECT EXISTS(SELECT id … )`，不取整行（决策 7） |
| `create(**values)` | 白名单校验 → `model(**payload)` → `session.add` → `flush()`（雪花 ID / 审计事件 / 版本初值即时生效）；返回实体，**不 commit** |
| `update(item_id, **values)` | 白名单校验 → 作用域内取行（缺失返回 `None`）→ `setattr` → `flush()` 并在 `_guard_version` 内转译 `StaleDataError → ConcurrentConflictError`（409） |
| `delete(item_id)` | `soft_delete_enabled=True` 走软删除，否则走硬删除（决策 5：默认软删 + 显式出口） |
| `soft_delete(item_id)` | 作用域内取行 → `model.soft_delete()`（置 `deleted_at`）→ `flush()`；返回是否存在 |
| `hard_delete(item_id)` | 作用域内取行 → `session.delete` → `flush()`（回收站物理清理 / 运维出口） | 

**写入字段严格白名单**（决策 3）：

- 仅接受模型映射列；未知键、非映射属性一律 `ConfigError`。
- 拒绝 `id` / `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version`（审计与内部字段不得手动赋值，统一由 ORM 事件、`soft_delete()` 与 `version_id_col` 维护）。

**租户写入口径**（决策 4，`tenant_scoped=True` 且上下文租户有主键时）：

- `create`：`values` 未带 `tenant_id` 自动注入上下文租户主键；已带且与上下文不一致抛 `ConfigError`（禁止跨租户写）。
- `update`：出现 `tenant_id` 即抛 `ConfigError`（禁止跨租户搬移）。
- 上下文租户无主键（内置兜底路径）不注入，与读侧 `_tenant_condition` 口径一致。

**乐观锁触发**（决策 6）：`update` / `soft_delete` / `hard_delete` 均在 `flush()` 处经 `version_id_col` 比对；冲突由 `_guard_version` 统一转 `ConcurrentConflictError`（HTTP 409），服务层无需各自处理 `StaleDataError`。

**内存基线差异**（决策 18）：`BaseMemoryRepository` 保持硬删，作为测试替身不实现软删除；`soft_delete` / `hard_delete` 在 `BaseScopedRepository` 提供默认别名（默认委托 `delete`），DB 实现覆写——差异在基类 docstring 注明。

### 4.4 分页与排序 <a id="pagination"></a>

- `list_page(query)`：`_resolve_sort(query)`（白名单）→ ORDER BY → `LIMIT size OFFSET (page-1)*size`；`total` 仍由 `count()` 单独计算（`BaseService.page` 契约不变）。
- `list_cursor(query)`：偏移口径 `LIMIT limit OFFSET int(cursor)`（与 `BaseService.cursor_page` 的游标语义一致）；keyset 游标键升级归 01_04。
- `_apply_sort` 基础版：白名单字段 → 模型列对象（`_column` 校验）→ `asc()` / `desc()`；未知字段忽略；全部被忽略时回落 `id ASC` 保证稳定序。**四库 NULLS 口径、排序字段索引配合与分页限深（100 页）归 01_04**。
- `sortable_fields` 白名单机制沿用契约层 `_resolve_sort`，`_apply_sort` 不接触用户原始输入。

### 4.5 `BaseModel` 落库验证 <a id="base-model"></a>

阶段一已交付的 `BaseModel`（`app/models/base.py`）保持字段与事件实现不变，本任务在**异步会话 + 仓储 flush 链路**下验证并登记：

| 能力 | 实现机制（已交付） | 本任务验证点 |
| --- | --- | --- |
| 雪花 ID | `id` 列 `default=id_generator.next_id`（BIGINT 主键，网络侧转字符串） | 异步 flush 后 ID 为正且唯一 |
| 审计字段 | `before_insert` / `before_update` ORM 事件填充（`current_user_id` 上下文） | 异步会话下自动填充、更新刷新 `updated_at/by` 且保留 `created_at` |
| 软删除 | `deleted_at`（NULL=未删）+ `soft_delete()` / `restore()`；查询默认过滤 | 仓储软删后 `get` / `list` 不可见、唯一键释放 |
| 乐观锁 | `version_id_col`（版本比对 / 自增，冲突 `StaleDataError`） | 异步并发旧版本 flush 抛错并经仓储转 409 |

- `BaseModel` docstring 的四库类型映射表按 4.6 实测值回写（布尔行修正、多值行补充）。

### 4.6 四库类型映射与软删除复合唯一索引 <a id="dialect"></a>

以 SQLAlchemy 方言编译器**离线编译**代表模型（`SysModule` + 类型探针表）的 `CREATE TABLE` 断言映射（不连真库）：

| 字段口径 | SQLite | MySQL | PostgreSQL | 达梦 DM8 |
| --- | --- | --- | --- | --- |
| `id` / `*_id`（BIGINT） | BIGINT | BIGINT | BIGINT | BIGINT |
| `*_at`（DateTime） | DATETIME | DATETIME | TIMESTAMP WITHOUT TIME ZONE | DATETIME |
| `Integer` / `version` | INTEGER | INTEGER | INTEGER | INTEGER |
| `SmallInteger` | SMALLINT | SMALLINT | SMALLINT | SMALLINT |
| `String(n)` | VARCHAR(n) | VARCHAR(n) | VARCHAR(n) | VARCHAR2(n CHAR) |
| `Text` | TEXT | TEXT | TEXT | TEXT |
| 布尔（`Boolean`） | BOOLEAN | BOOL（TINYINT(1)） | BOOLEAN | SMALLINT |
| 多值（`JSON`） | JSON | JSON | JSON | JSON |

- **布尔口径**（决策 12）：维持 SQLAlchemy `Boolean`——四库均落为各自布尔 / 小整数等价形式，符合《数据库开发规范》「布尔 tinyint/smallint/BOOLEAN」允许范围；前端真 / 假 / 未设置三态与 `1/0 ↔ 布尔` 归一口径不变，回写《架构设计 · 数据架构》与 `BaseModel` 文档（原「PostgreSQL SMALLINT」「小整数 1/0」表述按实测修正）。
- **多值口径**（决策 14）：多值字段以跨方言 `JSON` 类型存数组（与既有字典域模型一致）；接口仍按数组传输，标签类简单集合可继续逗号分隔字符串。
- **软删除复合唯一索引**：四库 DDL 均断言 `UNIQUE (唯一字段, deleted_at)` 存在；SQLite 真库验证「多个 NULL 共存 + 同键删除后复用 + 恢复不冲突」；PostgreSQL / MySQL / 达梦的 NULL 语义与 DDL 真库实测归 01_05。
- 达梦方言经 `dmSQLAlchemy` 注册（`create_engine("dm+dmPython://…")` 取 dialect，不建连；01_01 已接线同步引擎）。

### 4.7 索引命名规范修正 <a id="index-naming"></a>

`app/models/base.py` 的声明式基类改用带命名约定的元数据（决策 13）：

- `Base.metadata = MetaData(naming_convention={"ix": "idx_%(table_name)s_%(column_0_name)s"})`；`index=True` 生成的索引名由 `ix_<表>_<列>` 变为 `idx_<表>_<列>`（`idx_sys_module_deleted_at` 等），对齐《命名规范》「普通 `idx_字段`」与《数据库开发规范》「索引 idx_/uq_ 前缀」。
- 显式命名对象不受影响（唯一约束 `uq_*`、字典域显式 `Index("idx_*")` 均保持不变）；命名含表名前缀，避免 PostgreSQL / 达梦下同名列索引跨表重名。
- 迁移基线尚未落地（01_04），此刻修正避免错误索引名被固化进首个 revision；开发库文件经下次建表自然更新。

### 4.8 统一会话入口 `session_scope` 与迁移 <a id="session-scope"></a>

`app/db/session.py` 新增 `session_scope`（决策 17）：

| 项 | 约定 |
| --- | --- |
| 签名 | `async with session_scope(registry, *, db_key=None, read_only=False, factory=None) as session` |
| 库键 | `db_key` 为空时取 `current_tenant_context().db_key`（无上下文回落演示租户，与 dict / listing 现状一致）；显式传入则按库键取引擎 |
| 读写角色 | `registry.get(db_key, read_only=read_only)`；缺省主库（字典读写共用同一路径，避免写后读副本旧值） |
| 会话工厂 | `factory` 为空时新建 `SessionFactory()`；调用方可注入 |
| 事务 | 只负责建会话与释放；提交 / 回滚 / 事务边界仍归调用方（服务层工作单元） |

迁移范围（行为不变，仅会话入口收敛）：`app/dict/providers.py`、`app/dict/query.py`、`app/dict/service.py`、`app/dict/sql.py`（2 处）、`app/listing/store.py` 共 6 处 `_session` 改为 `async with session_scope(self._engines) as session: yield session`，并清理不再使用的 `async_sessionmaker` / `current_tenant_context` 导入。

### 4.9 `sys_module` 落库与幂等种子 <a id="seed"></a>

`ops/seed_module.py`（形态对齐 `ops/seed_tenant.py`，URL 解析复用其 `resolve_url`）：

- 目标库：`--url` > `BMS_MIGRATION_URL` > 配置 `database.platform.url`（平台库）。
- 执行：`SysModule.__table__.create(engine, checkfirst=True)` 幂等建表 → 按 `module_key` + `deleted_at is null` 判存，插入 `PLATFORM_MODULES`（sys / wf / rpt / ai，字段 `module_key` / `name` / `table_prefix` / `errcode_segment` / `event_domain` / `status`）——**单一来源**复用模块注册服务常量，避免种子与校验清单漂移。
- 输出 `[seed_module] 新增 N 行（幂等；重复执行输出 0）`；`--dry-run` 仅打印目标库与种子清单。
- `sys_module_i18n` 附表不在本任务种子范围（无消费方）；Alembic 迁移与 SQLite 全量自动建表归 01_04（就位后建表分支兼容保留）。

### 4.10 装配与调用面 <a id="assembly"></a>

- 仓储装配：模块仓储继承 `BaseDbRepository[Model]` 并声明 `model`，经 FastAPI 依赖注入会话构造，例如：
  - 写路径：`repository = XxxRepository(Depends(get_write_db))` / 事务内以 `get_uow` 的同一会话构造（FastAPI 依赖缓存保证同请求同会话）；
  - 读路径：`Depends(get_db)` 按只读标记选主 / 副本。
- 本任务不新增模块路由与业务仓储（首个消费方随通用能力模块接入）；`main.py` 装配无改动。
- `ops/seed_module.py` 在开发平台库执行一次（与 `seed_tenant.py` 同口径），为后续 03_01 服务目录升格准备数据。

## 5. 失败分支与边界 <a id="failures"></a>

| 场景 | 处理 |
| --- | --- |
| 作用域条件字段不在模型映射列 | `ConfigError`（快速失败，不静默丢条件） |
| 作用域条件操作符 / 值形态非法 | `ConfigError`（如 `in` 非序列、`like` 非字符串、`between` 非二元） |
| `in` 空序列 | 翻译为恒假条件（与内存基线一致） |
| 写入字段含未知键 | `ConfigError` |
| 写入字段含 `id` / 审计 / `version` / `deleted_at` | `ConfigError`（内部字段不得手动赋值） |
| `create` 显式 `tenant_id` 与上下文租户不一致 | `ConfigError`（禁止跨租户写） |
| `update` 携带 `tenant_id` | `ConfigError`（禁止跨租户搬移） |
| 模型无 `tenant_id` 列但 `tenant_scoped=True` | 读条件翻译 / create 注入处 `ConfigError`（声明与模型不符） |
| `update` / 软删 / 硬删目标不存在或不在作用域 | 返回 `None` / `False`（仓储层不抛业务异常） |
| 乐观锁冲突（`StaleDataError`） | `ConcurrentConflictError`（10004 / 409） |
| 主库不可用且请求为写 | 依赖层已抛 `DatabaseUnavailableError`（10006 / 503，01_01 口径），仓储不重复处理 |
| `soft_delete_enabled=False` 且调用 `soft_delete` | 仍软删除（显式出口要求模型具备 `deleted_at`，即 `BaseModel`）；`delete` 才按开关分流 |
| 内存基线调用 `soft_delete` | 默认别名委托 `delete`（硬删，测试替身差异，docstring 注明） |
| 排序字段全被忽略 | 回落 `id ASC` 保证稳定序 |
| 游标非数字 | 维持与 `BaseService.cursor_page` 同口径（keyset 游标与限深归 01_04） |
| `session_scope` 显式未知库键 | 由引擎注册表 / 工厂按既有口径处理（租户键非法 `ConfigError`） |

## 6. 测试设计与验收映射 <a id="tests"></a>

用例先登记 Kiwi TCMS（本任务登记 **1 条用例**，多条断言共用同一 `kiwi_id`，编号以平台回读为准，见第 9 节实施步骤）。

| Kiwi | 用例 | 类型 | 断言要点 |
| --- | --- | --- | --- |
| TBD | DB 仓储 CRUD 与作用域 | 单元（SQLite 真库） | create/get/list/count/exists/update；软删后不可见；数据范围条件；`like` / `in` / `between` 翻译 |
| TBD | 写入口径 | 单元 | 白名单拒绝未知键 / `id` / 审计 / `version` / `deleted_at`；租户 create 注入与不一致拒绝；update 禁改租户 |
| TBD | 删除出口 | 单元 | `delete` 软删（`soft_delete_enabled=True`）/ 硬删（`False`）；`hard_delete` 物理删除；`restore` 后恢复可见 |
| TBD | 乐观锁 | 单元 | 并发旧版本 flush → `ConcurrentConflictError`；版本号自增 |
| TBD | 分页与排序 | 单元 | `list_page` LIMIT/OFFSET；`list_cursor` 偏移；默认 `id ASC`；白名单排序生效、未知字段忽略 |
| TBD | 四库类型与复合唯一 | 单元 | 四方言 DDL 类型断言（含布尔 / JSON）；`UNIQUE (唯一字段, deleted_at)`；SQLite 多 NULL 共存与同键复用 |
| TBD | 索引命名 | 单元 | `index=True` 生成 `idx_{表}_{列}`；显式 `uq_*` / `idx_*` 不变 |
| TBD | 会话入口 | 单元 | `session_scope` 按库键 / 租户上下文取引擎、读写角色透传、自定义工厂 |
| TBD | `sys_module` 种子 | 单元 | 幂等建表 + 4 行平台域种子；重复执行新增 0；dry-run 输出 |
| TBD | dict / listing 回归 | 单元 | 会话入口迁移后既有字典 / 查询方案用例全绿 |

验收映射：

| 完成标准 | 验证方式 |
| --- | --- |
| `BaseRepository` 异步 CRUD 与分页用例通过 | DB 仓储用例（CRUD / 作用域 / 分页排序 / 存在性） |
| `BaseModel` 雪花 ID / 软删除 / 审计 / 乐观锁用例通过 | 仓储异步链路用例 + 既有 Kiwi 30 同步用例 |
| 四库类型映射与复合唯一索引验证通过 | 四方言 DDL 编译断言 + SQLite 真库 NULL 唯一用例 |
| `sys_module` 落库且种子正确 | `ops/seed_module.py` 幂等用例 + 开发平台库实测 |
| `pytest` / `ruff` / `pyright` 全绿 | 门禁命令（新增模块覆盖率 100%） |

## 7. 登记落点 <a id="registry-writeback"></a>

| 落点 | 内容 |
| --- | --- |
| 《后端基类清单》§2 / §5 / §8 / §10 | `BaseRepository` 契约（`soft_delete` / `hard_delete` 派生）、`BaseDbRepository` 真实实现与退出 `BaseStub`、`BaseStub` 使用方调整、`session_scope` 统一会话入口、继承链与状态回写 |
| 《后端开发规范》「SQL 与数据访问规范」 | 仓储写入字段白名单、软删除 / 硬删除出口、会话入口统一口径补充 |
| 《架构设计 · 数据架构》「数据规范」 | 布尔 / 多值字段存储口径回写（按实测映射与 JSON 数组口径） |
| 《数据库设计 · 数据表设计》`sys_module.md` | 状态与落库注记（种子先行、迁移归 01_04） |
| 计划 | §2 已完成表（01_03 行）与表头计数；§3 剩余任务移除 01_03 |
| 任务 / 父任务 | 状态两处一致（需求文档不承载进度） |
| Kiwi TCMS | 登记本任务策展用例并回读编号（`@pytest.mark.kiwi_id`） |
| 实施 / 测试记录 | 任务目录 `实施/`、`测试/` 各一份 |

## 8. 边界与开放项 <a id="boundary"></a>

- 归 01_04：排序契约 DB 侧（四库 NULLS 口径、排序字段索引配合、分页限深 100 页、keyset 游标键）、Alembic 三方言在线迁移、SQLite 全量自动建表、`ops` 批量迁移（`seed_module` 建表分支届时退化）。
- 归 01_05：三库真库集成、CI `verify/db` 档、达梦方言真库实测（复合唯一 NULL 语义、迁移 DDL、schema 前缀大小写、类型映射真库确认）。
- 归 03_01 / 03_02：`sys_module` 升格服务目录（服务维度 / 契约版本字段）、启动与 CI 接库唯一性校验。
- 归 RBAC 阶段：数据范围 `read_predicate` 真实规则注入与 `allow_write` 写前校验。
- 本任务只迁移 dict / listing 会话入口，不改其查询与写路径语义，不做模块仓储化。
- 开放项：模块仓储的依赖注入工厂（`Depends` 装配）随首个业务模块接入；达梦异步适配器归 01_05。

## 9. 实施步骤 <a id="steps"></a>

```mermaid
flowchart LR
    A["Kiwi 用例登记（先登记后编码）"] --> B[BaseDbRepository 真实实现]
    B --> C[BaseModel / 类型映射 / 索引命名]
    C --> D[session_scope + dict/listing 迁移]
    D --> E[sys_module 种子脚本]
    E --> F[用例编码 + 门禁 + 开发库实测]
    F --> G[登记回写 + 实施/测试记录 + 提交]
```

1. 读《KiwiTCMS部署使用说明》「用例约定」节，登记本任务用例并**回读编号**（输入文件落测试仓 `scripts/kiwi/cases/`）。
2. `BaseScopedRepository` 补 `soft_delete` / `hard_delete` 派生默认；`BaseDbRepository` 真实实现（会话注入 / 作用域 SQL / CRUD / 分页排序 / 白名单 / 租户口径 / 乐观锁）；退出 `BaseStub`。
3. `BaseModel` 映射表回写 + `Base.metadata` ix 命名模板；四方言类型映射用例。
4. `session_scope` 新增 + dict / listing 6 处 `_session` 迁移与导入清理。
5. `ops/seed_module.py` 幂等种子；开发平台库执行实测（重复执行为 0）。
6. 新增 / 适配用例（`@pytest.mark.kiwi_id`）；`uv run pytest` / `ruff` / `pyright` 全绿、新增模块覆盖率 100%。
7. 登记回写 + 实施 / 测试记录 + 代码与文档分开提交（`feat` / `docs`）；偏差与遗留闭环另提。

关键命令：

```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -q --cov=app --cov-branch
uv run python -m ops.seed_module
uv run python -m ops.check_modules
python3 scripts/tools/base-check/check-backend-base.py   # 仓库根
python3 scripts/tools/base-check/check-base.py
python3 scripts/tools/base-check/check-links.py
```

## 10. 决策记录（对齐记录） <a id="align"></a>

| # | 事项 | 结论（逐项确认） |
| --- | --- | --- |
| 1 | 仓储会话接入 | 构造注入 `AsyncSession`（`get_db` / `get_write_db` / `get_uow` 同请求同会话）；仓储不开关会话、不提交 |
| 2 | 仓储模型声明 | 类属性 `model: ClassVar[type[ModelT]]` |
| 3 | 写入字段口径 | 严格白名单：仅映射列；拒绝 `id` / 审计 / `version` / `deleted_at`，违规 `ConfigError` |
| 4 | 租户写入口径 | `tenant_scoped` 且上下文有主键：`create` 自动注入 / 校验，`update` 禁改 |
| 5 | delete 语义 | 另加出口：`delete` 默认软删（`soft_delete_enabled=True`）、`soft_delete` / `hard_delete` 显式方法 |
| 6 | 乐观锁触发 | ORM 更新 + `flush()`，`_guard_version` 统一转 `ConcurrentConflictError`（409） |
| 7 | `exists` | 覆写为 `SELECT EXISTS`（不取整行） |
| 8 | 默认排序 | 无 `sort` 时 `ORDER BY id ASC`（与内存基线一致） |
| 9 | 排序实现范围 | 基础 ORDER BY（白名单字段 → 模型列；未知忽略、全忽略回落 id）；四库 NULLS / 限深 / 索引配合归 01_04 |
| 10 | 游标分页范围 | 偏移口径 `LIMIT/OFFSET`（与 `BaseService.cursor_page` 一致）；keyset 游标键归 01_04 |
| 11 | 作用域非法字段 | 抛 `ConfigError` 快速失败（不静默丢条件） |
| 12 | 布尔口径 | 维持 `Boolean`，按实测回写四库映射（SQLite BOOLEAN / MySQL BOOL / PG BOOLEAN / 达梦 SMALLINT） |
| 13 | 索引命名 | `Base.metadata` 命名模板全局对齐 `idx_{表}_{列}` |
| 14 | 多值字段口径 | 跨方言 `JSON` 数组；接口按数组传输，标签类可逗号分隔 |
| 15 | 四库验证方式 | 离线编译四方言 DDL + SQLite 真库 NULL 唯一；三库真库归 01_05 |
| 16 | `sys_module` 种子 | 独立 `ops/seed_module.py`（复用 `PLATFORM_MODULES`；i18n 附表不在内） |
| 17 | 会话入口统一 | 新增 `session_scope` 并迁移 dict / listing 6 处 `_session` |
| 18 | 内存基线 delete | 保持硬删（测试替身差异在基类文档注明） |
| 19 | `BaseStub` 去留 | 移除（`BaseDbRepository` 不再是未实现桩；同步清单与继承链） |

## 11. 参考文档 <a id="ref"></a>

- [架构设计 · 后端基础类体系](../../../../../../设计/架构设计/04_架构设计_后端基础类体系.md)「各层基类与模块约定」「阶段交付与跨阶段基座契约」节
- [架构设计 · 数据访问与分片](../../../../../../设计/架构设计/13_架构设计_子系统_数据访问与分片.md)「多数据源管理」「读写分离」「事务边界规则」「查询规范」节
- [架构设计 · 数据架构](../../../../../../设计/架构设计/07_架构设计_数据架构.md)「数据规范」「回收站机制」节
- [后端基类清单](../../../../../../后端基类清单.md)「模块基类（数据访问 / 服务 / 契约 / 模型）」「数据访问与多租户基座」节
- [后端开发规范](../../../../../../规范/后端开发规范.md)「后端基座体系（强制）」「SQL 与数据访问规范」「异步与并发」节
- [数据库开发规范](../../../../../../规范/数据库开发规范.md)、[命名规范](../../../../../../规范/命名规范.md)
- [数据库设计 · sys_module](../../../../../../设计/数据库设计/数据表设计/sys_module.md)
- [01_01 数据访问底座落库详细设计](../../01_后端基座真实实现_01_数据访问底座落库/设计/01_详细设计_01_数据访问底座落库.md)、[01_02 多租户数据拓扑落库与实测详细设计](../../01_后端基座真实实现_02_多租户数据拓扑落库与实测/设计/01_详细设计_02_多租户数据拓扑落库与实测.md)
- [需求 01-3：BaseRepository 异步化与 DB 实现 + BaseModel 落库](../../../../需求/01_需求_后端基座真实实现.md#r01-3)

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写 · 关键决策逐项确认
