"""达梦 XA 自定义方言：两阶段事务经服务器端 `DBMS_XA` 包实现。

- DM8 服务器**支持 XA**（`DBMS_XA` 包：`XA_START / XA_END / XA_PREPARE / XA_COMMIT /
  XA_ROLLBACK / XA_RECOVER`），但 `dmSQLAlchemy` **同步**方言未接 `DBMS_XA`、`dmPython` DBAPI
  未暴露 TPC → 默认 `Connection.begin_twophase()` 抛 `NotImplementedError`。本方言以**纯 Python**
  补齐（**不改编译驱动**），等价 Java JDBC 的 XA RM 语义。
- **部署**：实例侧条件与参数见《达梦 DM8 部署使用说明》「两阶段事务（XA）实例条件」（应用侧无需配置）。
- 两阶段走**同步引擎**（SQLAlchemy 异步 API 不暴露两阶段）；达梦运行期本就经同步门面接入。
- **悬挂分支回收（05_07 补齐）**：`do_recover_twophase` 经 `TABLE(DBMS_XA.XA_RECOVER())` 列举悬挂分支，
  并以 `RAWTOHEX` 还原出**可回放的** `(gtrid, bqual)`；`_xid_raw` 对 `DMXARecoveredXid` **直接使用、不再哈希**
  ——否则「列举得出、驱动不了」（`blake2b` 派生不可逆）。
- 结论与登记见《数据库设计 · 方言特性 · 达梦》「事务与连接」与《后端基类清单》数据访问基座。
"""

from dataclasses import dataclass
from hashlib import blake2b
from typing import Any

from dmSQLAlchemy.dmpython import DMDialect_dmPython  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import text

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseValueObject

TMNOFLAGS = 0
"""`XA_START` 标志：新分支（`DBMS_XA.TMNOFLAGS`）。"""

TMSUCCESS = 0x04000000
"""`XA_END` 标志：成功结束分支（`DBMS_XA.TMSUCCESS`）。"""

RECOVER_SQL = "SELECT RAWTOHEX(gtrid) AS gtrid, RAWTOHEX(bqual) AS bqual FROM TABLE(DBMS_XA.XA_RECOVER())"
"""悬挂分支列举 SQL（返回 `RAW` 的十六进制串，供 `HEXTORAW` 原样还原）。"""


@dataclass(frozen=True)
class DMXARecoveredXid(BaseValueObject):
    """**可回放的**达梦悬挂分支标识（`gtrid` / `bqual` 为 `RAWTOHEX` 还原出的十六进制串）。

    `do_recover_twophase` 返回本类型而非派生摘要——恢复驱动时 `_xid_raw` 识别本类型并**直接使用**
    （不再 `blake2b` 派生），保证「列举 → 驱动 `commit` / `rollback`」闭环；值对象语义（不可变 / 按值相等）。
    """

    gtrid: str
    """全局事务标识的十六进制串（`RAWTOHEX` 结果）。"""

    bqual: str
    """分支限定符的十六进制串（`RAWTOHEX` 结果）。"""

    def __post_init__(self) -> None:
        """规范化（小写）。"""
        object.__setattr__(self, "gtrid", self.gtrid.lower())
        object.__setattr__(self, "bqual", self.bqual.lower())

    def __str__(self) -> str:
        """文本形态（`gtrid|bqual`，便于日志与排障）。"""
        return f"{self.gtrid}|{self.bqual}"


class DMXADialect(DMDialect_dmPython):
    """达梦 XA 方言：`do_*_twophase` 接 `DBMS_XA`。"""

    name = "dmxa"
    driver = "dmPython"
    supports_statement_cache = True

    @staticmethod
    def _xid_raw(xid: Any) -> tuple[str, str]:
        """由 SQLAlchemy xid 派生 (`gtrid`, `bqual`) 的十六进制串（各 8 字节，稳定、碰撞概率可忽略）。

        **可回放例外**：`xid` 为 `DMXARecoveredXid`（悬挂分支列举结果）时**直接使用**其
        `gtrid` / `bqual`，**不再哈希**——否则二次派生对不上原分支、恢复器驱动不了。

        Args:
            xid: SQLAlchemy 两阶段事务标识（字符串、对象或 `DMXARecoveredXid`）。

        Returns:
            tuple[str, str]: （`gtrid` hex, `bqual` hex），供 `HEXTORAW` 转 `RAW(8)`。
        """
        if isinstance(xid, DMXARecoveredXid):
            return xid.gtrid, xid.bqual
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

    def matches_recovered_xid(self, xid: Any, recovered: Any) -> bool:
        """判定悬挂分支列举项是否对应给定 `xid`（按 `_xid_raw` 派生后的 `gtrid|bqual` 比对）。

        Args:
            xid: 目标分支标识（TM 分配的 `xid` 文本）。
            recovered: `do_recover_twophase` 返回项（`DMXARecoveredXid`）。

        Returns:
            bool: 对应同一分支为 True。
        """
        gtrid, bqual = self._xid_raw(xid)
        return str(recovered) == f"{gtrid}|{bqual}"

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
        """提交全局事务（必要时先 `prepare`，再 `XA_COMMIT`）。

        `recover=True`（恢复驱动悬挂分支）时 `xid` 应为 `do_recover_twophase` 返回的
        `DMXARecoveredXid`，且分支已 `PREPARE`（`is_prepared=True`）。
        """
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
        """列举达梦悬挂 / 启发式完成的分支（**可回放**）。

        经 `TABLE(DBMS_XA.XA_RECOVER())` 取回悬挂分支，并以 `RAWTOHEX` 还原 `gtrid` / `bqual`
        为 `DMXARecoveredXid`——可直接回传 `do_commit_twophase` / `do_rollback_twophase`
        驱动协议完成（`_xid_raw` 对可回放载体不再哈希）。

        Args:
            connection: SQLAlchemy 连接（方言契约同 `do_*_twophase`）。

        Returns:
            list[Any]: 悬挂分支标识列表（`DMXARecoveredXid`；无悬挂为空表）。
        """
        rows = connection.execute(text(RECOVER_SQL)).fetchall()
        xids: ConcurrentStableList[Any] = ConcurrentStableList()
        for row in rows:
            gtrid = row[0]
            bqual = row[1]
            if gtrid is None or bqual is None:
                continue
            xids.add(DMXARecoveredXid(str(gtrid), str(bqual)))
        return list(xids)
