"""自定义 SQLAlchemy 方言（数据访问基座）。

导入本包即完成方言注册（**进程级**，仅注册名→模块映射，按需惰性加载）：

- `dmxa`：达梦两阶段事务（XA）方言——服务器端 `DBMS_XA` 包承载，纯 Python 继承
  `dmSQLAlchemy` 同步方言（**不改编译驱动**），详见 `dm_xa.py`。
"""

from sqlalchemy.dialects import registry

registry.register("dmxa", "bms_core.db.dialects.dm_xa", "DMXADialect")
registry.register("dmxa.dmPython", "bms_core.db.dialects.dm_xa", "DMXADialect")
