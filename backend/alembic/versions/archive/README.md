# 归档链（`archive`）— 空链占位

本目录承载**归档库**（`bms_archive`）的迁移脚本，当前为空链：

- 归档库建库与只读流转机制见《架构设计 · 数据访问与分片》与《架构设计 · 审计哈希链》；
- 归档表（归档策略 / 归档日志等）随**归档阶段**落地，届时在此新增 `0001_*.py`
  （`branch_labels=("archive",)`），并在 `app/db/migration.py` 的 `ARCHIVE_TABLES` 登记表集；
- 空链下执行 `uv run alembic -n alembic:archive upgrade head` 会输出
  「链 archive 暂无迁移脚本（跳过）」并正常退出（不建表、不报错）。
