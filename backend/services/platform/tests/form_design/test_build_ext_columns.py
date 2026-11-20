"""自建字段补建列脚本（`ops.build_ext_columns`）：建列 / 幂等 / 失败置 failed / 预演 / 入口码。

**为什么整文件独占库**：被测对象就是「给表加列 + 回写状态」，必须真造表、真执行 DDL；
共享库上改结构会破坏并行 worker 的断言，也与「结构只由数据初始化一次建好」的口径冲突。
"""

import asyncio
from typing import Any

import pytest
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConfigError
from bms_core.models.platform.form_design import (
    DDL_STATUS_ACTIVE,
    DDL_STATUS_FAILED,
    DDL_STATUS_PENDING,
    SysFieldExt,
)
from ops import build_ext_columns as module
from ops.build_ext_columns import build_library, main
from tests_support.form_design import create_probe_table, list_columns
from tests_support.shared_access import shared_session

pytestmark = pytest.mark.own_db(
    "补建列脚本要真造表 / 真加列 / 真回写状态：结构变更只允许在独占临时库，共享库结构由数据初始化建好"
)

_TABLE = "biz_ext_probe"


def _argv(*items: str) -> ConcurrentStableList[str]:
    """命令行参数（`main` 的口径是插入序集合，不是裸 list）。

    Args:
        *items: 参数项。

    Returns:
        ConcurrentStableList[str]: 参数清单。
    """
    return ConcurrentStableList(items)


def _seed_pending(
    url: str,
    *,
    field_key: str,
    form_code: str = "wbuild",
    table: str = _TABLE,
    with_table: bool = True,
) -> int:
    """在独占库造一条待建列字段（可选先建目标探针表）。

    Args:
        url: 独占租户库连接串。
        field_key: 字段键（列名派生为 `ext_{field_key}`）。
        form_code: 表单标识（同一表单内键唯一，重放场景换一个）。
        table: 目标物理表名。
        with_table: 是否先重建目标探针表（False 用于「列已存在」重放）。

    Returns:
        int: 字段主键。
    """

    async def _run() -> int:
        if with_table:
            await create_probe_table(url, table)
        async with shared_session(url, read_only=False) as session:
            row = SysFieldExt(
                form_code=form_code,
                field_key=field_key,
                name="补充",
                type="text",
                option_set_key=None,
                column_name=f"ext_{field_key}",
                table_name=table,
                ddl_status=DDL_STATUS_PENDING,
                sort=0,
                status="enabled",
            )
            session.add(row)
            await session.flush()
            field_id = int(row.id)
            await session.commit()
        return field_id

    return asyncio.run(_run())


def _status(url: str, field_id: int) -> str:
    """读字段当前 `ddl_status`。

    Args:
        url: 独占租户库连接串。
        field_id: 字段主键。

    Returns:
        str: 状态值。
    """

    async def _run() -> str:
        async with shared_session(url, read_only=True) as session:
            row = (await session.execute(select(SysFieldExt).where(SysFieldExt.id == field_id))).scalar_one()
            return str(row.ddl_status)

    return asyncio.run(_run())


def _columns(url: str, table: str = _TABLE) -> ConcurrentStableList[str]:
    """读目标表现有列名。

    Args:
        url: 独占租户库连接串。
        table: 表名。

    Returns:
        ConcurrentStableList[str]: 列名。
    """
    return asyncio.run(list_columns(url, table))


def test_build_creates_column_and_marks_active(isolated_tenant: str) -> None:
    """待建列 → 真加列 → 回写 active（幂等脚本的主路径）。"""
    field_id = _seed_pending(isolated_tenant, field_key="demo")
    result = asyncio.run(build_library(isolated_tenant, dry_run=False))
    assert (result.scanned, result.built, result.skipped) == (1, 1, 0)
    assert len(result.failed) == 0
    assert "ext_demo" in _columns(isolated_tenant)
    assert _status(isolated_tenant, field_id) == DDL_STATUS_ACTIVE


def test_build_hits_existing_column_without_error(isolated_tenant: str) -> None:
    """列已存在时按幂等命中（不重复加列、不报错）。"""
    _seed_pending(isolated_tenant, field_key="idem")
    assert asyncio.run(build_library(isolated_tenant, dry_run=False)).built == 1
    _seed_pending(isolated_tenant, field_key="idem", form_code="wreplay", with_table=False)
    replay = asyncio.run(build_library(isolated_tenant, dry_run=False))
    assert (replay.scanned, replay.built, replay.skipped) == (1, 0, 1)
    assert len(replay.failed) == 0


def test_build_marks_failed_when_target_table_missing(isolated_tenant: str) -> None:
    """目标表不存在 → 该字段置 failed，失败明细带字段标识（不中断其它字段）。"""
    field_id = _seed_pending(isolated_tenant, field_key="missing", table="biz_absent", with_table=False)
    result = asyncio.run(build_library(isolated_tenant, dry_run=False))
    assert len(result.failed) == 1
    assert "wbuild.missing" in result.failed[0]
    assert _status(isolated_tenant, field_id) == DDL_STATUS_FAILED


def test_dry_run_only_scans(isolated_tenant: str, capsys: pytest.CaptureFixture[str]) -> None:
    """预演只打印待建列，不改结构、不改状态。"""
    field_id = _seed_pending(isolated_tenant, field_key="preview")
    result = asyncio.run(build_library(isolated_tenant, dry_run=True))
    assert (result.scanned, result.built, result.skipped) == (1, 0, 0)
    assert "待建列 wbuild.preview" in capsys.readouterr().out
    assert "ext_preview" not in _columns(isolated_tenant)
    assert _status(isolated_tenant, field_id) == DDL_STATUS_PENDING


def test_main_returns_exit_code(isolated_tenant: str) -> None:
    """入口码：全部成功 0；存在失败 1（单库 `--url` 模式）。"""
    _seed_pending(isolated_tenant, field_key="ok")
    assert main(_argv("--url", isolated_tenant)) == 0
    _seed_pending(isolated_tenant, field_key="bad", table="biz_absent_2", with_table=False)
    assert main(_argv("--url", isolated_tenant)) == 1


def test_main_rejects_missing_target() -> None:
    """既未指定 `--code` 也未指定 `--all-tenants` → 明确报错。"""
    with pytest.raises(ConfigError):
        main(_argv())


def test_main_requires_service_when_resolving_by_code() -> None:
    """按编码解析库键但没有服务标识 → 明确报错。"""
    with pytest.raises(ConfigError):
        main(_argv("--code", "demo"))


def test_main_enumerates_all_tenants(isolated_tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--all-tenants` 经注册库枚举租户；结果逐库汇总（此处用替身固定到独占库）。"""

    class _FakeFactory:
        """引擎工厂替身：解析出的库键即独占库连接串。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def resolved_url(self, _key: str) -> str:
            return isolated_tenant

    class _Ref:
        """租户引用替身（只用到 `code` / `db_basis`）。"""

        def __init__(self, code: str) -> None:
            self.code = code
            self.db_basis = code

    async def _refs(_url: str) -> ConcurrentStableList[Any]:
        return ConcurrentStableList((_Ref("demo"),))

    monkeypatch.setattr(module, "EngineFactory", _FakeFactory)
    monkeypatch.setattr(module, "tenant_refs", _refs)
    monkeypatch.setenv("BMS_APP__SERVICE", "platform")
    _seed_pending(isolated_tenant, field_key="every")
    assert main(_argv("--all-tenants", "--service", "platform")) == 0


def test_build_library_summary_properties(isolated_tenant: str) -> None:
    """汇总结果：`built` / `failed` 按库累加（含多库）。"""
    _seed_pending(isolated_tenant, field_key="sum", table="biz_absent_3", with_table=False)
    first = asyncio.run(build_library(isolated_tenant, dry_run=False))
    result = module.BuildResult(libraries=ConcurrentStableList((first, first)))
    assert result.built == first.built * 2
    assert result.failed == 2


def test_guard_rejects_shared_db(tenant_db: str) -> None:
    """共享库上改结构直接报错（指向独占库夹具，而不是静默破坏并行数据）。"""
    with pytest.raises(RuntimeError, match="拒绝在共享库"):
        asyncio.run(create_probe_table(tenant_db, "biz_should_not_exist"))


def test_main_resolves_by_code_without_registry_hit(isolated_tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """按编码解析：注册库无该租户时回落编码作库名基（离线可用）。"""

    class _FakeFactory:
        """引擎工厂替身：任何库键都解析到独占库。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def resolved_url(self, _key: str) -> str:
            return isolated_tenant

    async def _no_refs(_url: str) -> ConcurrentStableList[Any]:
        return ConcurrentStableList()

    monkeypatch.setattr(module, "EngineFactory", _FakeFactory)
    monkeypatch.setattr(module, "tenant_refs", _no_refs)
    _seed_pending(isolated_tenant, field_key="bycode")
    assert main(_argv("--code", "demo", "--service", "platform")) == 0


def test_main_falls_back_when_registry_unreadable(
    isolated_tenant: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """注册库不可读：打印提示并回落编码作库名基（演练 / 离线可用）。"""

    class _Factory:
        """引擎工厂替身：平台注册库键抛错，租户库键返回独占库。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def resolved_url(self, key: str) -> str:
            if key.startswith("platform"):
                raise RuntimeError("registry down")
            return isolated_tenant

    monkeypatch.setattr(module, "EngineFactory", _Factory)
    _seed_pending(isolated_tenant, field_key="fb")
    assert main(_argv("--code", "demo", "--service", "platform")) == 0
    assert "租户注册库不可读" in capsys.readouterr().out
