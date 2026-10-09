"""达梦 XA 自定义方言：两阶段事务经服务器端 `DBMS_XA` 包实现。

- DM8 服务器**支持 XA**（`DBMS_XA` 包：`XA_START / XA_END / XA_PREPARE / XA_COMMIT /
  XA_ROLLBACK / XA_RECOVER`），但 `dmSQLAlchemy` **同步**方言未接 `DBMS_XA`、`dmPython` DBAPI
  未暴露 TPC → 默认 `Connection.begin_twophase()` 抛 `NotImplementedError`。本方言以**纯 Python**
  补齐（**不改编译驱动**），等价 Java JDBC 的 XA RM 语义。
- **部署**：实例侧条件与参数见《达梦 DM8 部署使用说明》「两阶段事务（XA）实例条件」（应用侧无需配置）。
- 两阶段走**同步引擎**（SQLAlchemy 异步 API 不暴露两阶段）；达梦运行期本就经同步门面接入。
- 结论与登记见《数据库设计 · 方言特性 · 达梦》「事务与连接」与《后端基类清单》数据访问基座。
"""

from hashlib import blake2b
from typing import Any

from dmSQLAlchemy.dmpython import DMDialect_dmPython  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import text

TMNOFLAGS = 0
"""`XA_START` 标志：新分支（`DBMS_XA.TMNOFLAGS`）。"""

TMSUCCESS = 0x04000000
"""`XA_END` 标志：成功结束分支（`DBMS_XA.TMSUCCESS`）。"""


class DMXADialect(DMDialect_dmPython):
    """达梦 XA 方言：`do_*_twophase` 接 `DBMS_XA`。"""

    name = "dmxa"
    driver = "dmPython"
    supports_statement_cache = True

    @staticmethod
    def _xid_raw(xid: Any) -> tuple[str, str]:
        """由 SQLAlchemy xid 派生 (`gtrid`, `bqual`) 的十六进制串（各 8 字节，稳定、碰撞概率可忽略）。

        Args:
            xid: SQLAlchemy 两阶段事务标识（字符串或对象）。

        Returns:
            tuple[str, str]: （`gtrid` hex, `bqual` hex），供 `HEXTORAW` 转 `RAW(8)`。
        """
        digest = blake2b(str(xid).encode("utf-8"), digest_size=16).digest()
        return digest[:8].hex(), digest[8:].hex()

    def _xa(self, connection: Any, xid: Any, statements: str) -> None:
        """在 `DBMS_XA_XID` 变量 `x` 上执行一段 PL/SQL，返回码非 0（`XA_OK=0`）即抛错。

        注意：达梦 `DBMS_XA_XID(<INTEGER>)` 为 **32 位**，大值会报「数据溢出」；故用
        `DBMS_XA_XID(FORMATID, GTRID, BQUAL)` 的 **RAW** 形态承载 64 位标识。

        Args:
            connection: SQLAlchemy 连接（两阶段方法接收的连接对象）。
            xid: 两阶段事务标识。
            statements: 引用 `x` 的 PL/SQL 语句片段（`r` 为 INT 返回码变量）。

        Raises:
            sqlalchemy.exc.DBAPIError: PL/SQL 内 `RAISE_APPLICATION_ERROR`（携 `DBMS_XA` 返回码）。
        """
        gtrid, bqual = self._xid_raw(xid)
        connection.execute(
            text(
                f"DECLARE x DBMS_XA_XID := DBMS_XA_XID(1, HEXTORAW('{gtrid}'), HEXTORAW('{bqual}')); r INT; "
                f"BEGIN {statements} IF r != 0 THEN RAISE_APPLICATION_ERROR(-20000, 'DMXA rc=' || r); END IF; END;"
            )
        )

    def do_begin_twophase(self, connection: Any, xid: Any) -> None:
        """开启两阶段分支（`XA_START`）。"""
        self._xa(connection, xid, f"r := DBMS_XA.XA_START(x, {TMNOFLAGS});")

    def do_prepare_twophase(self, connection: Any, xid: Any) -> None:
        """准备提交（`XA_END` → `XA_PREPARE`）。"""
        self._xa(
            connection,
            xid,
            f"r := DBMS_XA.XA_END(x, {TMSUCCESS}); IF r = 0 THEN r := DBMS_XA.XA_PREPARE(x); END IF;",
        )

    def do_commit_twophase(self, connection: Any, xid: Any, is_prepared: bool = True, recover: bool = False) -> None:
        """提交全局事务（必要时先 `prepare`，再 `XA_COMMIT`）。"""
        if not is_prepared:
            self.do_prepare_twophase(connection, xid)
        self._xa(connection, xid, "r := DBMS_XA.XA_COMMIT(x, FALSE);")

    def do_rollback_twophase(self, connection: Any, xid: Any, is_prepared: bool = True, recover: bool = False) -> None:
        """回滚分支（未 `prepare` 时先 `XA_END`，再 `XA_ROLLBACK`）。"""
        if not is_prepared:
            self._xa(connection, xid, f"r := DBMS_XA.XA_END(x, {TMSUCCESS});")
        self._xa(connection, xid, "r := DBMS_XA.XA_ROLLBACK(x);")

    # bare-collections:allow（覆写 SQLAlchemy 方言契约，返回类型须与基类 `Dialect` 一致）
    def do_recover_twophase(self, connection: Any) -> list[Any]:
        """列举悬挂 / 启发式完成的分支。

        本期不实现悬挂分支回收（策略归任务 05_06），恒返回空表。

        Returns:
            list[Any]: 分支标识列表（本期为空）。
        """
        return []
