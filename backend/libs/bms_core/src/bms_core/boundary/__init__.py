"""数据所有权边界能力域（boundary）：跨服务库访问的静态硬校验与运行时守卫。

- `directory`：表前缀归属（以服务目录 `SERVICE_CATALOG` 为单一来源）。
- `sql`：原始 SQL 表名与操作提取（标准库）。
- `exceptions`：读侧出口例外登记白名单契约（加载 / 校验 / 匹配）。
- `assess`：越界判定纯函数（静态校验与运行时守卫同源）。
- `base` / `table` / `null`：守卫契约、真实实现与缺省实现（插件键 `data_ownership_guard`）。

本 `__init__` 保持**轻量**（仅文档字符串，不导入子模块）：精简 CI（`base-integrity` 的
python:3.14-slim）经 `bms_core.boundary.directory` / `sql` / `exceptions` / `assess` 复用归属与
SQL 解析能力，导入链只依赖标准库与服务目录；重依赖（fastapi / sqlalchemy）仅在 `base` / `table` 内。
"""
