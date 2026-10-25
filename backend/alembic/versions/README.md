# 迁移清单目录（按业务域 × 数据源）

本目录是**表结构变更清单**的脚本仓库（07C `03_02`）。一条清单 = 一个业务域的全部结构变更脚本，
域内线性、域间互不引用；**拆 / 合部署单元不切清单**（只是"跑哪些清单"变了）。

## 目录规则

```text
alembic/versions/
├── platform_registry/          # 业务域标识（domain_key，snake_case）
│   ├── platform/               # 数据源段：平台服务库
│   └── tenant/                 # 数据源段：服务租户库
├── user/
│   └── tenant/
└── archive/archive/            # 归档库：单清单，不按域拆（表集为空）
```

- 清单名 = `{domain}/{datasource}` 两级目录，对应配置段 `[alembic:{domain}:{datasource}]` 与清单名
  `{domain}:{datasource}`；
- 目录**按需创建**：某域首次有结构变更时再建 `{domain}/{datasource}/` 并补 `alembic.ini` 段，
  不预置空目录（避免 16 域 × 3 数据源的噪音）。

## 版本记录表（每清单一张）

| 清单 | 版本记录表 |
| --- | --- |
| `{domain}:platform` / `{domain}:tenant` | `alembic_version_{domain}`（在各自库里，同名不冲突） |
| `archive:archive` | `alembic_version_archive` |

表名由域标识拼成（域标识已是 snake_case，无需引号）；`alembic/env.py` 按清单显式设置
`version_table`。**多域同库时互不覆盖**——这正是每清单独立一张的原因。

## 新增一条清单

1. 建目录 `alembic/versions/{domain}/{datasource}/`；
2. 在 `backend/alembic.ini` 补段 `[alembic:{domain}:{datasource}]`（`version_locations` 指向该目录）；
3. 放第一个脚本（`revision` 清单内独立递增，`branch_labels` 取清单名）;
4. 域必须已登记在 `deploy/boundaries/domain_layout.json`，且脚本操作的表归属该域
   （执行期校验会逐个脚本核对目标表归属）。

## 存量库切换

旧的服务级 `alembic_version` 保留只读一版，不迁移历史；域清单首次执行前做结构对账，
对账通过即写基线行（不重放 DDL），口径见 07C `03_02` 详细设计「存量库切换」节。
