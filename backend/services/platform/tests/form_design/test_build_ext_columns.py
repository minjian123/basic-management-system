"""自建字段补建列脚本（`ops.build_ext_columns`）：生成段内容 + 执行段结果。

口径（13_10 需求第 5 条）：结构变更不走运行期 DDL。**生成段**是纯逻辑（`build_script`），
产物就是迁移脚本内容；**执行段**（`build_in_session`）由初始化阶段真实跑一次。

本文件断言生成内容（列名 / 类型 / 幂等跳过 / 非法标识符），并用共享平台库上的一次真实执行
验证「建列 + 状态回写 + 失败置 failed」；用例自造字段与列，跑完清除。
"""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.dialects import sqlite

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.models.platform.form_design import (
    DDL_STATUS_ACTIVE,
    DDL_STATUS_FAILED,
    DDL_STATUS_PENDING,
    SysFieldExt,
)
from ops import build_ext_columns as module
from ops.build_ext_columns import (
    BuildResult,
    apply_script,
    build_in_session,
    build_script,
    main,
    script_statements,
    verify_applied,
)
from tests_support.form_design import create_probe_table
from tests_support.shared_access import shared_session

pytestmark = pytest.mark.xdist_group("form-design")

_TABLE = "biz_ext_probe"


def _argv(*items: str) -> ConcurrentStableList[str]:
    """命令行参数（`main` 口径是插入序集合）。"""
    return ConcurrentStableList(items)


def _field(
    field_key: str,
    *,
    form_code: str = "wbuild",
    table: str = _TABLE,
    type_: str = "text",
) -> SysFieldExt:
    """构造一条待建列字段（不落库时主键由默认生成器给出）。"""
    return SysFieldExt(
        form_code=form_code,
        field_key=field_key,
        name="补充",
        type=type_,
        option_set_key=None,
        column_name=f"ext_{field_key}",
        table_name=table,
        ddl_status=DDL_STATUS_PENDING,
        sort=0,
        status="enabled",
    )


def _script(
    fields: ConcurrentStableList[SysFieldExt],
    *,
    existing: ConcurrentStableDict[str, ConcurrentStableFrozenList[str]] | None = None,
) -> ConcurrentStableList[module.ScriptEntry]:
    """调生成段（默认无已存在列）。"""
    present = existing if existing is not None else ConcurrentStableDict[str, ConcurrentStableFrozenList[str]]()
    return build_script(fields, present, dialect=sqlite.dialect())


def test_build_script_renders_add_column() -> None:
    """生成段：待建列产出一条加列语句（含目标表 / 列名）。"""
    entries = _script(ConcurrentStableList((_field("demo"),)))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.skipped is False
    assert entry.table_name == _TABLE
    assert entry.column_name == "ext_demo"
    assert _TABLE in entry.sql and "ext_demo" in entry.sql


def test_build_script_skips_existing_column() -> None:
    """生成段：列已存在 → 标记跳过且不产出语句。"""
    existing: ConcurrentStableDict[str, ConcurrentStableFrozenList[str]] = ConcurrentStableDict(
        {"biz_ext_probe": ConcurrentStableFrozenList(("ext_idem",))}
    )
    entries = _script(ConcurrentStableList((_field("idem"),)), existing=existing)
    assert entries[0].skipped is True
    assert entries[0].sql == ""


def test_build_script_maps_field_types() -> None:
    """生成段：不同字段类型产出不同列类型（脚本内容随类型变化）。"""
    fields = ConcurrentStableList((_field("t_text", type_="text"), _field("t_num", type_="number")))
    entries = _script(fields)
    assert all(entry.sql for entry in entries)
    assert entries[0].sql != entries[1].sql


def test_build_script_rejects_invalid_table() -> None:
    """生成段：非法表名直接拒绝（不生成语句）。"""
    with pytest.raises(ParamError, match="物理表名非法"):
        _script(ConcurrentStableList((_field("bad", table="bad;drop"),)))


def test_build_script_rejects_invalid_column() -> None:
    """生成段：非法列名直接拒绝。"""
    field = _field("bad")
    field.column_name = "not_prefixed"
    with pytest.raises(ParamError, match="物理列名非法"):
        _script(ConcurrentStableList((field,)))


def _seed_pending(url: str, *, field_key: str, form_code: str = "wbuild", table: str = _TABLE) -> int:
    """在共享平台库造一条待建列字段（已提交；用例结束自行清除）。"""

    async def _run() -> int:
        async with shared_session(url, read_only=False) as session:
            row = _field(field_key, form_code=form_code, table=table)
            session.add(row)
            await session.flush()
            field_id = int(row.id)
            await session.commit()
        return field_id

    return asyncio.run(_run())


def _cleanup(url: str, *, field_key: str, form_code: str = "wbuild", drop_column: bool = False) -> None:
    """清除本用例造的字段行（可选删掉建出的列）。"""
    asyncio.run(_cleanup_async(url, field_key=field_key, form_code=form_code, drop_column=drop_column))


async def _cleanup_async(url: str, *, field_key: str, form_code: str = "wbuild", drop_column: bool = False) -> None:
    """清除本用例造的字段行（异步版；async 用例内用）。"""
    async with shared_session(url, read_only=False) as session:
        if drop_column:
            await session.execute(text(f'ALTER TABLE "{_TABLE}" DROP COLUMN "ext_{field_key}"'))
        await session.execute(
            delete(SysFieldExt).where(SysFieldExt.form_code == form_code, SysFieldExt.field_key == field_key)
        )
        await session.commit()


async def test_declared_change_applied_at_init(shared_tenant_db_url: str) -> None:
    """变更声明前置：初始化阶段生成的列已生效（用例只验证结果）。"""
    async with shared_session(shared_tenant_db_url, read_only=False) as session:

        def _collect(sync_session: Any) -> ConcurrentStableList[str]:
            inspector = inspect(sync_session.get_bind())
            return ConcurrentStableList(str(item["name"]).lower() for item in inspector.get_columns(_TABLE))

        columns = await session.run_sync(_collect)
        rows = (
            (
                await session.execute(
                    select(SysFieldExt.ddl_status).where(
                        SysFieldExt.form_code == "probe_biz", SysFieldExt.field_key == "seeded"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert "ext_seeded" in columns
    assert list(rows) == [DDL_STATUS_ACTIVE]


def test_script_record_matches_declared_changes() -> None:
    """初始化实际执行的脚本落盘：与声明逐条对应，回执与生成一致（不再靠语义推断）。"""
    from tests_support.form_design_changes import CHANGES, read_script_record

    record = read_script_record()
    entries = ConcurrentStableList(record["entries"])
    executed = ConcurrentStableList(record["executed"])
    labels = ConcurrentStableFrozenSet(str(entry["label"]) for entry in entries)
    assert ConcurrentStableFrozenSet(f"{change.form_code}.{change.field_key}" for change in CHANGES) <= labels
    # 回执 == 生成脚本非跳过语句（初始化阶段自检的同一判据，测试再断一次）
    assert executed == ConcurrentStableList(str(entry["sql"]) for entry in entries if not entry["skipped"])
    expected = build_script(
        ConcurrentStableList(
            tuple(
                _field(change.field_key, form_code=change.form_code, table=change.table, type_=change.type)
                for change in CHANGES
            )
        ),
        ConcurrentStableDict(),
        dialect=sqlite.dialect(),
    )
    expected_sqls = ConcurrentStableFrozenSet(entry.sql for entry in expected if not entry.skipped)
    for entry in entries:
        if entry["skipped"]:
            continue
        assert str(entry["sql"]) in expected_sqls
        assert str(entry["table"]) in str(entry["sql"])
        assert str(entry["column"]) in str(entry["sql"])


async def test_apply_script_matches_generated_statements(platform_db_url: str) -> None:
    """一致性：执行回执 == 生成脚本非跳过语句；执行后结构回读无缺失。"""
    field_key = f"eq{uuid.uuid4().hex[:6]}"
    async with shared_session(platform_db_url, read_only=False) as session:
        row = _field(field_key)
        session.add(row)
        await session.flush()
        await session.commit()
        script = build_script(
            ConcurrentStableList((row,)),
            ConcurrentStableDict(),
            dialect=session.get_bind().dialect,
        )
        try:
            applied = await apply_script(session, script)
            assert applied.executed == script_statements(script)
            assert len(applied.executed) == 1
            assert await verify_applied(session, script) == ConcurrentStableList()
        finally:
            await _cleanup_async(platform_db_url, field_key=field_key, drop_column=True)


async def test_verify_applied_reports_missing_column(platform_db_url: str) -> None:
    """一致性：脚本声明了列但库中没有 → 回读报缺失（不静默通过）。"""
    field = _field(f"miss{uuid.uuid4().hex[:6]}", table=f"biz_absent_{uuid.uuid4().hex[:6]}")
    async with shared_session(platform_db_url, read_only=False) as session:
        script = build_script(
            ConcurrentStableList((field,)),
            ConcurrentStableDict(),
            dialect=session.get_bind().dialect,
        )
        missing = await verify_applied(session, script)
    assert missing == ConcurrentStableList((f"{field.table_name}.ext_{field.field_key}",))


async def test_build_in_session_creates_column_and_marks_active(platform_db_url: str) -> None:
    """执行段：真加列 → 回写 active（共享库上跑一次，跑完删列删行）。"""
    field_key = f"mk{uuid.uuid4().hex[:6]}"
    async with shared_session(platform_db_url, read_only=False) as session:
        row = _field(field_key)
        session.add(row)
        await session.flush()
        field_id = int(row.id)
        await session.commit()
        scanned, built, _skipped, failed = await build_in_session(session, dry_run=False)
    try:
        assert scanned >= 1
        assert built >= 1
        assert len(failed) == 0
        async with shared_session(platform_db_url, read_only=False) as session:

            def _collect(sync_session: Any) -> ConcurrentStableList[str]:
                inspector = inspect(sync_session.get_bind())
                return ConcurrentStableList(str(item["name"]).lower() for item in inspector.get_columns(_TABLE))

            columns = await session.run_sync(_collect)
            status = (
                await session.execute(select(SysFieldExt.ddl_status).where(SysFieldExt.id == field_id))
            ).scalar_one()
        assert f"ext_{field_key}" in columns
        assert status == DDL_STATUS_ACTIVE
    finally:
        await _cleanup_async(platform_db_url, field_key=field_key, drop_column=True)


async def test_build_in_session_marks_failed_when_table_missing(platform_db_url: str) -> None:
    """执行段：目标表不存在 → 该字段置 failed（共享库上跑一次，跑完删行）。"""
    field_key = f"bad{uuid.uuid4().hex[:6]}"
    table = f"biz_absent_{uuid.uuid4().hex[:6]}"
    async with shared_session(platform_db_url, read_only=False) as session:
        row = _field(field_key, table=table)
        session.add(row)
        await session.flush()
        field_id = int(row.id)
        await session.commit()
        _, _, _, failed = await build_in_session(session, dry_run=False)
    try:
        assert any(f"wbuild.{field_key}" in item for item in failed)
        async with shared_session(platform_db_url, read_only=False) as session:
            status = (
                await session.execute(select(SysFieldExt.ddl_status).where(SysFieldExt.id == field_id))
            ).scalar_one()
        assert status == DDL_STATUS_FAILED
    finally:
        await _cleanup_async(platform_db_url, field_key=field_key)


async def test_build_in_session_dry_run_only_prints(platform_db_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    """执行段：预演只输出脚本内容，不建列、不改状态。"""
    field_key = f"dry{uuid.uuid4().hex[:6]}"
    async with shared_session(platform_db_url, read_only=False) as session:
        row = _field(field_key)
        session.add(row)
        await session.flush()
        field_id = int(row.id)
        await session.commit()
        scanned, built, _skipped, failed = await build_in_session(session, dry_run=True)
    try:
        assert scanned >= 1
        assert built == 0
        assert len(failed) == 0
        assert f"待建列 wbuild.{field_key}" in capsys.readouterr().out
        async with shared_session(platform_db_url, read_only=False) as session:

            def _collect(sync_session: Any) -> ConcurrentStableList[str]:
                inspector = inspect(sync_session.get_bind())
                return ConcurrentStableList(str(item["name"]).lower() for item in inspector.get_columns(_TABLE))

            columns = await session.run_sync(_collect)
            status = (
                await session.execute(select(SysFieldExt.ddl_status).where(SysFieldExt.id == field_id))
            ).scalar_one()
        assert f"ext_{field_key}" not in columns
        assert status == DDL_STATUS_PENDING
    finally:
        await _cleanup_async(platform_db_url, field_key=field_key)


def test_main_returns_exit_code(platform_db_url: str) -> None:
    """入口码：预演成功 0；缺少目标 1。"""
    field_key = f"cli{uuid.uuid4().hex[:6]}"
    _seed_pending(platform_db_url, field_key=field_key)
    try:
        assert main(_argv("--url", platform_db_url, "--dry-run")) == 0
    finally:
        _cleanup(platform_db_url, field_key=field_key)
    assert main(_argv("--service", "platform")) == 1


def test_main_rejects_missing_target(capsys: pytest.CaptureFixture[str]) -> None:
    """既未指定 `--code` 也未指定 `--all-tenants` → 明确报错并返回 1。"""
    assert main(_argv("--service", "platform")) == 1
    assert "需 `--code` 或 `--all-tenants`" in capsys.readouterr().out


def test_main_requires_service_when_resolving_by_code(capsys: pytest.CaptureFixture[str]) -> None:
    """按编码解析库键但没有服务标识 → 明确报错并返回 1。"""
    assert main(_argv("--code", "demo")) == 1
    assert "需 `--service`" in capsys.readouterr().out


def test_main_enumerates_all_tenants(platform_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--all-tenants` 经注册库枚举租户；预演逐库汇总。"""

    class _FakeFactory:
        """引擎工厂替身：解析出的库键即共享平台库连接串。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def resolved_url(self, _key: str) -> str:
            return platform_db_url

    class _Ref:
        """租户引用替身（只用到 `code` / `db_basis`）。"""

        def __init__(self, code: str) -> None:
            self.code = code
            self.db_basis = code

    async def _refs(_url: str) -> ConcurrentStableList[Any]:
        return ConcurrentStableList((_Ref("demo"),))

    field_key = f"all{uuid.uuid4().hex[:6]}"
    _seed_pending(platform_db_url, field_key=field_key)
    monkeypatch.setattr(module, "EngineFactory", _FakeFactory)
    monkeypatch.setattr(module, "tenant_refs", _refs)
    monkeypatch.setenv("BMS_APP__SERVICE", "platform")
    try:
        assert main(_argv("--all-tenants", "--service", "platform", "--dry-run")) == 0
    finally:
        _cleanup(platform_db_url, field_key=field_key)


def test_build_library_summary_properties() -> None:
    """汇总结果：`built` 按库累加；`failed` 按失败条数累加。"""
    first = module.LibraryResult(
        url="fixture://wbuild",
        scanned=2,
        built=1,
        skipped=0,
        failed=ConcurrentStableList(("wbuild.bad：boom",)),
    )
    result = BuildResult(libraries=ConcurrentStableList((first, first)))
    assert result.built == 2
    assert result.failed == 2


def test_guard_rejects_shared_db(tenant_db: str) -> None:
    """共享库上改结构直接报错（指向独占库夹具，而不是静默破坏并行数据）。"""
    with pytest.raises(RuntimeError, match="拒绝在共享库"):
        asyncio.run(create_probe_table(tenant_db, "biz_should_not_exist"))
