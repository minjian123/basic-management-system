"""db 层：异步引擎、会话工厂与读写分离路由（engine.py / session.py）。

职责：数据库连接与会话生命周期。
禁止：写业务逻辑；会话禁止跨请求共享。
"""

# 注册自定义方言（`dmxa` 达梦 XA 等）：导入 db 层即生效（进程级）。
from bms_core.db import dialects as _dialects  # noqa: F401
