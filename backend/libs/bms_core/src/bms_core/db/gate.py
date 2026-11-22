"""数据库访问门钩子：生产默认直通，测试基座注入跨进程读写门（13_08）。

为什么放在生产侧：`db/session.py` 不能依赖 `bms_core.testing`（测试基座是可选面，运行镜像不装）。
这里只留一个可替换的钩子——生产进程不注入（零开销），测试会话由启动插件在 `pytest_configure`
注入读写门，使「所有数据库读写都在门上排队」只有一份实现，且会话入口不必区分运行环境。
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Final

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseFrameworkObject

GateHook = Callable[[str, bool, "float | None", "str | None"], AbstractAsyncContextManager[None]]
"""门钩子签名：（数据源键, 是否只读, 等待上限, 实际库连接串）→ 异步上下文管理器。

为什么要带实际库连接串（2026-11-22）：门按**库**排队，不按数据源段排队——同一个数据源段
在用例里可能指向共享测试库，也可能指向 `own_db` / `tmp_path` 建的一次性库。只按数据源段
取名，私有库的建表会占住全局写门（实测 `apply_unit_schema` 在临时库上建全套表持门 >5s，
把 24 路其它 worker 全挡在 5s 上限外）。连接串为 None 时钩子按数据源段回落（生产直通路径
与显式写区间不需要它）。
"""


@asynccontextmanager
async def _null_transaction(session: LazyGatedSession) -> AsyncGenerator[None]:
    """空事务上下文：退出时提交（SQLite 测试会话「不考虑事务、写完立即提交」的 `begin()` 替身）。

    Args:
        session: 写门代理会话（用于退出时经门提交）。

    Yields:
        None: 事务区间（不开启真实事务）。

    Raises:
        BaseException: 区间内异常原样抛出（先尽力回滚，回滚对 autocommit 是空操作）。
    """
    try:
        yield
    except BaseException:
        with contextlib.suppress(Exception):
            await session.rollback()
        raise
    else:
        await session.commit()


GATE_CRITICAL_WAIT: Final = 10.0
"""整段临界区的等门上限（秒）：建表、用例级独占、显式写区间等「整段」场景用它。

与单次写的短上限（5s）分工：单次写是毫秒级，等超几秒就是有长占用，报错更有用；
整段临界区本身合法地要跑若干秒，故给到 10s（2026-11-21 由 30s 收到 10s：测试等待超过 10s
即视为用例问题，立即失败并点名持有者）。
"""

_hook: GateHook | None = None
"""已注入的门钩子；None 表示直通（生产默认）。"""


def set_gate_hook(hook: GateHook | None) -> None:
    """注入或清除门钩子（测试基座在会话起始调用）。

    Args:
        hook: 门钩子；None 清除。
    """
    global _hook
    _hook = hook


def current_gate_hook() -> GateHook | None:
    """取当前门钩子（诊断与自测用）。

    Returns:
        GateHook | None: 门钩子；未注入为 None。
    """
    return _hook


@asynccontextmanager
async def db_access_gate(
    db_key: str, *, read_only: bool, wait: float | None = None, url: str | None = None
) -> AsyncGenerator[None]:
    """数据库访问门（未注入钩子时直通）。

    Args:
        db_key: 数据源键（平台库键或租户库键）。
        read_only: 是否只读（只读取读门，写取写门）。
        wait: 等待上限（秒）；None 走门的默认。
        url: 本次操作实际指向的库连接串；None 表示调用方不掌握（钩子按数据源段回落）。

    Yields:
        None: 门内区间。
    """
    hook = _hook
    if hook is None:
        yield
        return
    async with hook(db_key, read_only, wait, url):
        yield


class _ScalarProxy(BaseFrameworkObject):
    """物化后的标量结果代理：`Result.scalars()` 的常用只读接口。

    读操作在 `execute` 里已把行取完并放门，这里只做内存访问，不再持任何锁。
    """

    def __init__(self, values: ConcurrentStableList[Any]) -> None:
        """初始化。

        Args:
            values: 已物化的标量值。
        """
        self._values = values

    def all(self) -> ConcurrentStableList[Any]:
        """全部值（副本）。"""
        return ConcurrentStableList(self._values)

    def first(self) -> Any | None:
        """首个值；空结果返回 None。"""
        return self._values[0] if self._values else None

    def one(self) -> Any:
        """唯一值。

        Raises:
            ValueError: 结果不是恰好一条。
        """
        if len(self._values) != 1:
            raise ValueError(f"期望恰好一条标量结果，实际 {len(self._values)} 条")
        return self._values[0]

    def one_or_none(self) -> Any | None:
        """零或一条；多条抛错。

        Raises:
            ValueError: 结果多于一条。
        """
        if len(self._values) > 1:
            raise ValueError(f"期望最多一条标量结果，实际 {len(self._values)} 条")
        return self._values[0] if self._values else None

    def unique(self) -> _ScalarProxy:
        """去重占位（结果已物化，本实现原样返回）。"""
        return self

    def __iter__(self) -> Iterator[Any]:
        """迭代。"""
        return iter(self._values)

    def __len__(self) -> int:
        """条数。"""
        return len(self._values)


class _MappingsProxy(BaseFrameworkObject):
    """物化后的字典视图代理：`Result.mappings()` 的常用只读接口。"""

    def __init__(self, rows: ConcurrentStableList[Any]) -> None:
        """初始化。

        Args:
            rows: 已物化的行。
        """
        self._rows = rows

    def all(self) -> ConcurrentStableList[Any]:
        """全部行映射（副本）。"""
        return ConcurrentStableList(row._mapping for row in self._rows)

    def first(self) -> Any | None:
        """首个行映射；空结果返回 None。"""
        return self._rows[0]._mapping if self._rows else None

    def __iter__(self) -> Iterator[Any]:
        """迭代行映射。"""
        return iter([row._mapping for row in self._rows])


class ResultProxy(BaseFrameworkObject):
    """物化后的结果代理：读操作的门已放，所有访问都是内存操作。

    为什么要物化：读操作的语义是「取锁 → 立即读 → 取完即放」。SQLAlchemy 的 `AsyncResult`
    是惰性的，若把门跟到结果消费完，游标会长时间占库、写者只能等满上限；因此在门内一次性
    取完行，再用本代理提供常用只读接口。
    """

    def __init__(self, rows: ConcurrentStableList[Any], *, rowcount: int = -1) -> None:
        """初始化。

        Args:
            rows: 已物化的行。
            rowcount: 受影响行数（非 DML 为 -1）。
        """
        self._rows = rows
        self.rowcount = rowcount

    @property
    def returns_rows(self) -> bool:
        """是否返回行（物化后恒为 True）。"""
        return True

    def all(self) -> ConcurrentStableList[Any]:
        """全部行（副本）。"""
        return ConcurrentStableList(self._rows)

    def fetchall(self) -> ConcurrentStableList[Any]:
        """同 `all()`。"""
        return self.all()

    def first(self) -> Any | None:
        """首行；空结果返回 None。"""
        return self._rows[0] if self._rows else None

    def one(self) -> Any:
        """唯一行。

        Raises:
            ValueError: 结果不是恰好一条。
        """
        if len(self._rows) != 1:
            raise ValueError(f"期望恰好一条结果，实际 {len(self._rows)} 条")
        return self._rows[0]

    def one_or_none(self) -> Any | None:
        """零或一条行；多条抛错。

        Raises:
            ValueError: 结果多于一条。
        """
        if len(self._rows) > 1:
            raise ValueError(f"期望最多一条结果，实际 {len(self._rows)} 条")
        return self._rows[0] if self._rows else None

    def scalars(self) -> _ScalarProxy:
        """取首列标量视图。"""
        return _ScalarProxy(ConcurrentStableList(row[0] for row in self._rows))

    def scalar(self) -> Any | None:
        """首行首列。"""
        return self._rows[0][0] if self._rows else None

    def scalar_one(self) -> Any:
        """唯一标量。

        Raises:
            ValueError: 结果不是恰好一条。
        """
        return self.scalars().one()

    def scalar_one_or_none(self) -> Any | None:
        """零或一条标量。

        Raises:
            ValueError: 结果多于一条。
        """
        return self.scalars().one_or_none()

    def mappings(self) -> _MappingsProxy:
        """字典视图。"""
        return _MappingsProxy(self._rows)

    def unique(self) -> ResultProxy:
        """去重占位（结果已物化，本实现原样返回）。"""
        return self

    def keys(self) -> ConcurrentStableList[str]:
        """列名清单。"""
        if not self._rows:
            return ConcurrentStableList()
        return ConcurrentStableList(self._rows[0]._mapping.keys())

    def close(self) -> None:
        """关闭占位（已无底层游标）。"""

    def __iter__(self) -> Iterator[Any]:
        """迭代行。"""
        return iter(self._rows)

    def __len__(self) -> int:
        """行数。"""
        return len(self._rows)


class ReadOperationGatedSession(BaseFrameworkObject):
    """把读门收窄到**每次读操作**：取读门 → 开短会话 → 取完结果 → 关会话 → 放门。

    **每次读操作都新开一个短会话**：只把游标关掉时，SQLite 读事务会留到长会话关闭，
    24 路并行下写者在写门里等库锁满 10 秒（表现为「拿着写门 10 秒」）。短会话退出即回滚并
    关闭连接，读锁必然释放，读门与 SQLite 事务的生命周期完全一致。

    生产（未注钩子）不会创建本类，零开销。
    """

    def __init__(
        self,
        scope_factory: Callable[[], AbstractAsyncContextManager[None]],
        session_factory: Callable[[], AbstractAsyncContextManager[object]],
        bind: object | None = None,
    ) -> None:
        """初始化。

        Args:
            scope_factory: 门上下文工厂（每次读操作新建一个）。
            session_factory: 会话工厂（每次读操作新建短会话，退出即关闭并结束事务）。
            bind: 底层绑定引擎（供 `session.bind` 只读读取；不参与取门）。
        """
        object.__setattr__(self, "_scope_factory", scope_factory)
        object.__setattr__(self, "_session_factory", session_factory)
        object.__setattr__(self, "_bind", bind)

    @property
    def bind(self) -> object | None:
        """底层绑定引擎（与普通会话的 `bind` 同义；读操作仍按次开短会话）。

        Returns:
            object | None: 绑定引擎；调用方未提供时为 None。
        """
        return object.__getattribute__(self, "_bind")

    def get_bind(self) -> object | None:
        """取绑定引擎（SQLAlchemy 会话协议的兼容入口）。

        Returns:
            object | None: 绑定引擎。
        """
        return object.__getattribute__(self, "_bind")

    def __getattr__(self, name: str) -> Any:
        """代理属性：只暴露读路径方法，其余明确报错（避免误用长会话）。

        Args:
            name: 属性名。

        Returns:
            Any: 包装后的读方法。

        Raises:
            AttributeError: 非读路径方法。
        """
        if name in {"execute", "scalars", "scalar", "get", "stream", "stream_scalars"}:

            async def _read_call(*args: object, **kwargs: object) -> Any:
                """转交到门内读操作。"""
                return await self._read(name, *args, **kwargs)

            return _read_call
        raise AttributeError(f"读会话不提供 {name}：读操作按次开短会话，仅支持 execute / scalars / scalar / get")

    async def _read(self, name: str, *args: object, **kwargs: object) -> Any:
        """门内执行一次读操作：开短会话 → 取完结果 → 关会话（事务随之结束）。

        Args:
            name: 底层会话方法名。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            Any: 物化后的结果或方法返回值。

        Raises:
            NotImplementedError: 流式结果（门无法跟到消费结束）。
        """
        if name in {"stream", "stream_scalars"}:
            raise NotImplementedError("读门按操作取放不支持流式结果；请改用 execute / scalars")
        scope_factory = object.__getattribute__(self, "_scope_factory")
        session_factory = object.__getattribute__(self, "_session_factory")
        async with scope_factory(), session_factory() as session:
            if name == "get":
                return await session.get(*args, **kwargs)
            if name == "scalar":
                return await session.scalar(*args, **kwargs)
            result = await session.execute(*args, **kwargs)
            rowcount = int(getattr(result, "rowcount", -1))
            rows = ConcurrentStableList(result.all())
            result.close()
        if name == "scalars":
            return ResultProxy(rows, rowcount=rowcount).scalars()
        return ResultProxy(rows, rowcount=rowcount)

    async def aclose(self) -> None:
        """关闭占位（读会话按次开关，没有长会话需要关闭）。"""

    def __repr__(self) -> str:
        """诊断用表示。

        Returns:
            str: 表示串。
        """
        return "ReadOperationGatedSession(per-operation)"


class LazyGatedSession(BaseFrameworkObject):
    """写会话的**操作级**门代理：每个写操作取写门、执行完立即放。

    为什么不做会话级 / 事务级：会话级会把「等审计、组装响应、拼参数」全算进临界区；事务级会
    把事务中间的空档也占着。业主口径（2026-11-21）是「取写锁后必须立即写」——门的作用域就是
    一次数据库方法调用。生产（未注钩子）不会创建本类，零开销。

    Attributes:
        info: 底层会话的 `info`（SQLAlchemy 内部也读它）。
    """

    def __init__(
        self,
        scope_factory: Callable[[], AbstractAsyncContextManager[None]],
        session: object,
        bind: object | None = None,
    ) -> None:
        """初始化。

        Args:
            scope_factory: 门上下文工厂（每次写操作新建一个）。
            session: 底层会话对象。
            bind: 对外暴露的绑定引擎（SQLite autocommit 包装下保留原始引擎身份）。
        """
        object.__setattr__(self, "_scope_factory", scope_factory)
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_bind", bind)

    @property
    def bind(self) -> object:
        """绑定引擎：调用方给了原始引擎就用它，否则透传底层会话的 `bind`。

        Returns:
            object: 绑定引擎。
        """
        bind = object.__getattribute__(self, "_bind")
        return bind if bind is not None else object.__getattribute__(object.__getattribute__(self, "_session"), "bind")

    def begin(self) -> AbstractAsyncContextManager[object]:
        """**不开启显式事务**，但退出时提交（业主口径：每条 SQL 立即提交）。

        为什么要覆盖：应用代码里的 `session.begin()` 会在 AUTOCOMMIT 连接上显式开事务，
        事务跨多次读写期间一直占着 SQLite 库级写锁；别的写者拿到数据库门后仍被 SQLite
        挡在 `busy_timeout` 里，表现为「写门等超 5 秒」。测试口径是不考虑事务、写完立即提交，
        故这里不开事务；但 `begin()` 的语义是「退出即提交」，所以退出时仍 flush + commit，
        否则 `session.add` 之后的改动会丢在会话里。

        Returns:
            AbstractAsyncContextManager[object]: 退出即提交的空事务上下文。
        """
        return _null_transaction(self)

    def get_bind(self) -> object:
        """取绑定引擎（SQLAlchemy 会话协议的兼容入口）。

        Returns:
            object: 绑定引擎。
        """
        return self.bind

    def __getattr__(self, name: str) -> Any:
        """代理属性：协程方法逐个包门，其余原样返回。

        Args:
            name: 属性名。

        Returns:
            Any: 属性值或包装后的方法。
        """
        attr = getattr(object.__getattribute__(self, "_session"), name)
        if not inspect.iscoroutinefunction(attr):
            return attr

        async def _call(*args: object, **kwargs: object) -> object:
            async with object.__getattribute__(self, "_scope_factory")():
                return await attr(*args, **kwargs)

        return _call

    async def aclose(self) -> None:
        """关闭底层会话（门已按操作放完，无需额外释放）。"""
        with contextlib.suppress(Exception):
            await object.__getattribute__(self, "_session").aclose()

    def __repr__(self) -> str:
        """诊断用表示。

        Returns:
            str: 表示串。
        """
        return f"LazyGatedSession({object.__getattribute__(self, '_session')!r})"
