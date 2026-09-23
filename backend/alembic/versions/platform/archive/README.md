# 归档链（`platform:archive`）— 空链占位

本目录承载**归档库**（`bms_archive`，**不服务化**，链名固定 `platform:archive`）的迁移脚本，当前为空链：

- 归档库建库与只读流转机制见《架构设计 · 数据访问与分片》与《架构设计 · 审计哈希链》；
- 归档表（归档策略 / 归档日志等）随**归档阶段**落地，届时在此新增 `0001_*.py`
  （`branch_labels=("platform:archive",)`），并在表归属登记（`bms_core/services/table_registry.py`）
  以 `datasource = archive` 登记表集（派生即自动进链）；
- 归档链**不含**基础设施表（发件箱三表仅进各服务的 `platform` / `tenant` 链）；
- 空链下执行 `uv run alembic -n alembic:platform:archive upgrade head` 会输出
  「链 platform:archive 暂无迁移脚本（跳过）」并正常退出（不建表、不报错）。
