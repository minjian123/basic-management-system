"""主库可用性标记与探测：主库故障只读降级的进程内状态。

- 主库连接失败（`OperationalError` / `InterfaceError`）经全局异常处理器 `mark_degraded`；
- 降级期间写路径先 `probe`，失败则拒绝写（`DatabaseUnavailableError`），成功即恢复；
- 读路径在降级态优先副本（见 `session.py`）。
"""

from sqlalchemy import text

from app.core.capability import BaseAsyncResource
from app.db.engine import EngineFactory
from app.db.registry import PLATFORM_DB_KEY


class PrimaryHealth(BaseAsyncResource):
    """主库可用性：进程内降级标记 + 探测恢复。"""

    def __init__(self, factory: EngineFactory) -> None:
        """初始化。

        Args:
            factory: 引擎工厂（探测经其取主引擎）。
        """
        self._factory = factory
        self._degraded: set[str] = set()

    def mark_degraded(self, db_key: str = PLATFORM_DB_KEY) -> None:
        """标记主库不可用（进入只读降级）。

        Args:
            db_key: 数据源键。
        """
        self._degraded.add(db_key)

    def mark_recovered(self, db_key: str = PLATFORM_DB_KEY) -> None:
        """清除主库不可用标记（恢复）。

        Args:
            db_key: 数据源键。
        """
        self._degraded.discard(db_key)

    def is_degraded(self, db_key: str = PLATFORM_DB_KEY) -> bool:
        """主库当前是否处于降级态。

        Args:
            db_key: 数据源键。

        Returns:
            bool: 降级 True。
        """
        return db_key in self._degraded

    async def probe(self, db_key: str = PLATFORM_DB_KEY) -> bool:
        """探测主库（`SELECT 1`）：成功清标记返回 True，失败置标记返回 False。

        Args:
            db_key: 数据源键。

        Returns:
            bool: 主库可用 True。
        """
        try:
            engine = self._factory.create(db_key, read_only=False)
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            self.mark_degraded(db_key)
            return False
        self.mark_recovered(db_key)
        return True

    async def aclose(self) -> None:
        """释放（清空标记，幂等）。"""
        self._degraded.clear()
