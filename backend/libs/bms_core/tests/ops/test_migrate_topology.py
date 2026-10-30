"""拓扑迁移运维入口用例（07C `04_02`）：参数、P1 结论、P1~P4 全程、断点、清理与安全闸门。

P1~P4 在 SQLite 上端到端跑（源库 `platform` 单元 × 租户 `demo` → 目标单元 `identity`）；P5 需要平台应用
生命周期与拓扑表，其服务层由平台侧用例覆盖，本套只锁「未跑 P4 不许切换」等闸门。
Kiwi 用例编号未取得，本轮不登记（见实施记录遗留）。
"""

import argparse
import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

import ops.migrate_topology as migrate_topology
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.bootstrap import apply_domains_schema
from bms_core.db.migration import DATASOURCE_TENANT
from bms_core.tenant.seed.tenant import seed_tenants

_SOURCE_DB = "bms_platform_demo.db"
"""源库文件名（`[app].service=platform` × 租户库名基 `demo`）。"""

_TARGET_DB = "bms_identity_demo.db"
"""目标库文件名（目标单元 `identity` × 租户库名基 `demo`）。"""


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把平台库 / 服务租户库指向临时目录并刷新配置（与其它 ops 用例同口径）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()
    get_settings().app.service = "platform"


async def _seed_source(tmp_path: Path) -> None:
    """建源库表并写入两条角色（其余域表留空，对账时 0 == 0）。

    Args:
        tmp_path: 临时目录。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / _SOURCE_DB}"
    await apply_domains_schema(["role"], DATASOURCE_TENANT, url, target="seed")
    engine = create_engine(f"sqlite:///{tmp_path / _SOURCE_DB}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO sys_role (id, form_key, code, name, status, role_type, "
                "created_at, updated_at, version) VALUES "
                "(1, 'role', 'admin', '管理员', 'enabled', 'system', "
                "'2026-10-30 00:00:00', '2026-10-30 00:00:00', 0),"
                "(2, 'role', 'auditor', '审计员', 'enabled', 'custom', "
                "'2026-10-30 00:00:00', '2026-10-30 00:00:00', 0)"
            )
    finally:
        engine.dispose()


async def _seed_platform(tmp_path: Path) -> None:
    """建平台侧库：租户注册（`tenant` 服务的平台库）、默认拓扑与能力授权（`platform` 的平台库）。

    Args:
        tmp_path: 临时目录。
    """
    tenant_url = f"sqlite+aiosqlite:///{tmp_path}/bms_tenant.db"
    await seed_tenants(tenant_url)
    platform_url = f"sqlite+aiosqlite:///{tmp_path}/bms_platform.db"
    await apply_domains_schema(["platform_registry"], "platform", platform_url, target="seed")
    engine = create_engine(f"sqlite:///{tmp_path}/bms_platform.db")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO sys_tenant_topology (id, tenant_id, domain_key, unit_key, topology_version, "
                "status, created_at, updated_at, version) VALUES "
                "(1, 0, 'role', 'platform', 1, 'enabled', '2026-10-30 00:00:00', '2026-10-30 00:00:00', 0),"
                "(2, 0, 'user', 'identity', 1, 'enabled', '2026-10-30 00:00:00', '2026-10-30 00:00:00', 0),"
                "(3, 0, 'permission_meta', 'platform', 1, 'enabled', "
                "'2026-10-30 00:00:00', '2026-10-30 00:00:00', 0)"
            )
            connection.exec_driver_sql(
                "INSERT INTO sys_capability_grant (id, capability_name, consumer_key, source, status, "
                "created_at, updated_at, version) VALUES "
                "(1, 'platform.role.list', 'biz', 'declared', 'enabled', "
                "'2026-10-30 00:00:00', '2026-10-30 00:00:00', 0),"
                "(2, 'platform.permission_meta.query', 'biz', 'declared', 'enabled', "
                "'2026-10-30 00:00:00', '2026-10-30 00:00:00', 0)"
            )
    finally:
        engine.dispose()


def _args(tmp_path: Path, *extra: str) -> ConcurrentStableList[str]:
    """构造基础参数（源单元 `/` 目标单元 `/` 租户 `/` 库名基 `/` 状态目录）。

    Args:
        tmp_path: 临时目录。
        extra: 追加参数。

    Returns:
        ConcurrentStableList[str]: 命令行参数。
    """
    base = [
        "--tenant",
        "demo",
        "--domain",
        "role",
        "--from-unit",
        "platform",
        "--to-unit",
        "identity",
        "--tenant-id",
        "0",
        "--db-basis",
        "demo",
        "--notice",
        "2026-12-05 20:00-21:00 停机，已提前 3 天告知",
        "--state-dir",
        str(tmp_path / "state"),
    ]
    return ConcurrentStableList([*base, *extra])


def test_steps_resolution_and_conflicts() -> None:
    """步骤归一：缺省 p1..p5、`--dry-run` 只 p1、`--verify-only` 只 p4、与 `--step` 互斥。"""
    parser = migrate_topology.build_parser()
    args = parser.parse_args(["--tenant", "demo", "--domain", "role", "--to-unit", "grpops"])
    assert list(migrate_topology._steps(args)) == ["p1", "p2", "p3", "p4", "p5"]  # pyright: ignore[reportPrivateUsage]  # 白盒断言参数归一

    dry = parser.parse_args(["--tenant", "demo", "--domain", "role", "--to-unit", "identity", "--dry-run"])
    assert list(migrate_topology._steps(dry)) == ["p1"]  # pyright: ignore[reportPrivateUsage]

    only = parser.parse_args(["--tenant", "demo", "--domain", "role", "--to-unit", "identity", "--verify-only"])
    assert list(migrate_topology._steps(only)) == ["p4"]  # pyright: ignore[reportPrivateUsage]

    both = parser.parse_args(
        ["--tenant", "demo", "--domain", "role", "--to-unit", "identity", "--dry-run", "--step", "p3"]
    )
    with pytest.raises(ConfigError, match="不能同时使用"):
        migrate_topology._steps(both)  # pyright: ignore[reportPrivateUsage]


def test_assertions_parsing() -> None:
    """业务断言：`名称=SQL` 解析；缺 `=` 或名称为空即报错。"""
    parsed = migrate_topology._assertions(  # pyright: ignore[reportPrivateUsage]
        ConcurrentStableList(["角色数=SELECT COUNT(*) FROM sys_role", "库存 = SELECT 1"])
    )
    assert [(item.name, item.sql) for item in parsed] == [
        ("角色数", "SELECT COUNT(*) FROM sys_role"),
        ("库存", "SELECT 1"),
    ]
    with pytest.raises(ConfigError, match="名称=SQL"):
        migrate_topology._assertions(ConcurrentStableList(["角色数"]))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ConfigError, match="名称=SQL"):
        migrate_topology._assertions(ConcurrentStableList(["=SELECT 1"]))  # pyright: ignore[reportPrivateUsage]


def test_dry_run_reports_plan_without_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run`：输出 P1 七条结论与计划的库，不建任何库文件，退出 0。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_topology.main(_args(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    for key in ("tenant", "domains", "tables", "target_unit", "target_db", "volume", "dependents", "notice"):
        assert key in out
    assert "dry-run 未连库" in out
    assert not (tmp_path / _SOURCE_DB).exists() and not (tmp_path / _TARGET_DB).exists()
    audit = (tmp_path / "state" / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit[-1])["tenant"] == "demo"


def test_precheck_blocks_same_unit_and_missing_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1 失败即停：源与目标同单元、`stop` 档缺告知留痕，均不产生变更。"""
    _prepare(tmp_path, monkeypatch)
    same = _args(tmp_path, "--to-unit", "platform")
    assert migrate_topology.main(same) == 1
    out = capsys.readouterr().out
    assert "源与目标同为 platform" in out and "P1 未通过" in out
    assert not (tmp_path / _TARGET_DB).exists()

    no_notice = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--domain",
            "role",
            "--from-unit",
            "platform",
            "--to-unit",
            "identity",
            "--db-basis",
            "demo",
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )
    assert migrate_topology.main(no_notice) == 1
    assert "缺 --notice" in capsys.readouterr().out


def test_full_flow_p1_to_p4_copies_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1~P4 全程：建表 → 搬数 → 对账绿；审计留痕落文件；重复执行幂等。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_source(tmp_path))
    args = _args(tmp_path, "--step", "p1", "--step", "p2", "--step", "p3", "--step", "p4")
    assert migrate_topology.main(args) == 0
    out = capsys.readouterr().out
    assert "建库建表" in out and "对账（第 1 轮）" in out and "审计留痕" in out

    engine = create_engine(f"sqlite:///{tmp_path / _TARGET_DB}")
    try:
        with engine.connect() as connection:
            roles = connection.exec_driver_sql("SELECT id, code FROM sys_role ORDER BY id").all()
    finally:
        engine.dispose()
    assert [tuple(row) for row in roles] == [(1, "admin"), (2, "auditor")]

    assert migrate_topology.main(args) == 0, "重复执行幂等"
    assert "复制 2 行" in capsys.readouterr().out


def test_verify_only_and_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--verify-only` 只对账；`--resume` 沿用进度（已完成表整表跳过）。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_source(tmp_path))
    assert migrate_topology.main(_args(tmp_path, "--verify-only")) == 1, "目标库为空时对账不通过"

    assert migrate_topology.main(_args(tmp_path, "--step", "p2", "--step", "p3")) == 0
    assert migrate_topology.main(_args(tmp_path, "--verify-only")) == 0
    resumed = migrate_topology.main(_args(tmp_path, "--step", "p3", "--resume"))
    assert resumed == 0
    out = capsys.readouterr().out
    assert "复制 0 行" in out, "进度标记完成后不再重复搬数"


def test_switch_gate_requires_p4_or_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P5 闸门：未同时跑 P4 时拒绝；单步 P5 无 `--confirm` 拒绝（不启动平台应用）。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_topology.main(_args(tmp_path, "--step", "p3", "--step", "p5")) == 1
    assert "P5 要求 P4 全绿" in capsys.readouterr().err

    assert migrate_topology.main(_args(tmp_path, "--step", "p5")) == 1
    assert "必须加 --confirm" in capsys.readouterr().err


def test_unregistered_target_unit_asks_for_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """未登记的目标单元：库键服务段无法识别，直接给出「先登记或给 --to-url」的可执行提示。"""
    _prepare(tmp_path, monkeypatch)
    unregistered = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--domain",
            "role",
            "--from-unit",
            "platform",
            "--to-unit",
            "grpops",
            "--db-basis",
            "demo",
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )
    assert migrate_topology.main(unregistered) == 1
    message = capsys.readouterr().err
    assert "未在服务目录登记" in message and "--to-url" in message


async def test_switch_merges_topology_and_records_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P5：拓扑整批替换（只改搬迁域）与发布清单写入在同一次调用内完成。"""
    captured = _install_switch_fakes(monkeypatch, skip_release=False)
    plan = _plan(tmp_path)
    result = await migrate_topology._switch(plan, _switch_args(tmp_path))  # pyright: ignore[reportPrivateUsage]

    assert result.passed
    assert "拓扑版本 2 → 3" in result.detail and "清单 #7（单元 identity）" in result.detail
    assert [(row.domain_key, row.unit_key) for row in captured.rows] == [
        ("role", "identity"),
        ("user", "platform"),
    ]
    assert captured.revisions is not None, "写入发布清单时带上结构 revision 读面"


async def test_switch_skip_release_only_writes_topology(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--skip-release`：只写拓扑，不写发布清单（演练用）。"""
    captured = _install_switch_fakes(monkeypatch, skip_release=True)
    plan = _plan(tmp_path)
    args = _switch_args(tmp_path)
    args.skip_release = True
    result = await migrate_topology._switch(plan, args)  # pyright: ignore[reportPrivateUsage]

    assert result.passed and "未写（--skip-release）" in result.detail
    assert captured.rows and captured.revisions is None


def _plan(tmp_path: Path) -> migrate_topology.MigrationPlan:
    """构造迁移计划（P5 用例只需单元与库名基）。

    Args:
        tmp_path: 临时目录。

    Returns:
        MigrationPlan: 迁移计划。
    """
    return migrate_topology.MigrationPlan(
        tenant_code="demo",
        tenant_id=0,
        db_basis="demo",
        domains=ConcurrentStableFrozenList(["role"]),
        source_unit="platform",
        target_unit="identity",
        strategy="stop",
        source_url=f"sqlite+aiosqlite:///{tmp_path}/source.db",
        target_url=f"sqlite+aiosqlite:///{tmp_path}/target.db",
    )


def _switch_args(tmp_path: Path) -> argparse.Namespace:
    """构造 P5 用例的命令行参数（只用到 `--skip-release` 与状态目录）。

    Args:
        tmp_path: 临时目录。

    Returns:
        argparse.Namespace: 解析后的参数。
    """
    return migrate_topology.build_parser().parse_args(
        ["--tenant", "demo", "--domain", "role", "--to-unit", "identity", "--state-dir", str(tmp_path / "state")]
    )


class _Captured:
    """P5 替身捕获到的入参（拓扑行与 revision 读面）。"""

    def __init__(self) -> None:
        """初始化空捕获。"""
        self.rows: ConcurrentStableList[migrate_topology.TopologyRow] = ConcurrentStableList()
        self.revisions: object = None


def _install_switch_fakes(monkeypatch: pytest.MonkeyPatch, *, skip_release: bool) -> _Captured:
    """把平台应用工厂、会话与两个服务替换为替身，捕获调用参数。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        skip_release: 是否让参数带上 `--skip-release`。

    Returns:
        _Captured: 捕获到的 `rows` 与 `revisions`。
    """
    captured = _Captured()

    class _FakeTopology:
        """替身：返回两域拓扑，替换后返回新版本。"""

        def __init__(self, session: object) -> None:
            """初始化。

            Args:
                session: 会话（忽略）。
            """
            del session

        async def export(self, tenant_id: int) -> tuple[int, ConcurrentStableList[SimpleNamespace]]:
            """导出当前拓扑。

            Args:
                tenant_id: 租户主键。

            Returns:
                tuple[int, ConcurrentStableList[SimpleNamespace]]: 版本与行。
            """
            assert tenant_id == 0
            return 2, ConcurrentStableList(
                [
                    SimpleNamespace(domain_key="role", unit_key="platform", status="enabled"),
                    SimpleNamespace(domain_key="user", unit_key="platform", status="enabled"),
                ]
            )

        async def replace(
            self, tenant_id: int, *, rows: ConcurrentStableList[migrate_topology.TopologyRow], note: str
        ) -> tuple[int, ConcurrentStableList[migrate_topology.TopologyRow]]:
            """整批替换（记录入参）。

            Args:
                tenant_id: 租户主键。
                rows: 新版本行。
                note: 说明。

            Returns:
                tuple[int, ConcurrentStableList[TopologyRow]]: 新版本与行。
            """
            del tenant_id, note
            captured.rows = rows
            return 3, rows

    class _FakeRelease:
        """替身：返回固定发布清单快照。"""

        def __init__(self, session: object, *, revisions: object) -> None:
            """初始化。

            Args:
                session: 会话（忽略）。
                revisions: 结构 revision 读面。
            """
            del session
            captured.revisions = revisions

        async def record(self, *, unit_key: str, topology_version: int, note: str) -> SimpleNamespace:
            """写入发布清单。

            Args:
                unit_key: 单元标识。
                topology_version: 拓扑版本。
                note: 摘要。

            Returns:
                SimpleNamespace: 清单快照。
            """
            assert topology_version == 3 and note
            return SimpleNamespace(manifest_version=7, unit_key=unit_key)

    class _FakeFactory:
        """替身：返回带 `router` / `state` 的假应用。"""

        def create(self, config: object) -> SimpleNamespace:
            """创建应用。

            Args:
                config: 配置（忽略）。

            Returns:
                SimpleNamespace: 假应用。
            """
            del config
            return SimpleNamespace(
                router=SimpleNamespace(lifespan_context=_noop_lifespan),
                state=SimpleNamespace(engine_registry=None, session_factory=None),
            )

    monkeypatch.setattr(migrate_topology, "ApplicationFactory", _FakeFactory)
    monkeypatch.setattr(migrate_topology, "TenantTopologyService", _FakeTopology)
    monkeypatch.setattr(migrate_topology, "ReleaseService", _FakeRelease)
    monkeypatch.setattr(migrate_topology, "session_scope", _fake_session_scope)
    return captured


def _noop_lifespan(app: object) -> AbstractAsyncContextManager[None]:
    """替身：空的应用生命周期。

    Args:
        app: 假应用。

    Returns:
        AbstractAsyncContextManager[None]: 上下文管理器。
    """
    del app

    @asynccontextmanager
    async def _context() -> AsyncGenerator[None]:
        """空上下文。

        Yields:
            None: 无值。
        """
        yield None

    return _context()


def _fake_session_scope(*args: object, **kwargs: object) -> AbstractAsyncContextManager[object]:
    """替身：不做真实连接的会话上下文。

    Args:
        args: 位置参数（忽略）。
        kwargs: 关键字参数（忽略）。

    Returns:
        AbstractAsyncContextManager[object]: 上下文管理器。
    """
    del args, kwargs

    @asynccontextmanager
    async def _context() -> AsyncGenerator[object]:
        """空会话。

        Yields:
            object: 占位会话。
        """
        yield object()

    return _context()


def test_plan_uses_registry_and_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1 取址：租户注册库给主键与库名基、拓扑给源单元、授权表给依赖方（不靠命令行兜底）。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_platform(tmp_path))
    args = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--domain",
            "role",
            "--to-unit",
            "identity",
            "--notice",
            "已告知",
            "--state-dir",
            str(tmp_path / "state"),
            "--step",
            "p1",
        ]
    )
    assert migrate_topology.main(args) == 0
    out = capsys.readouterr().out
    assert "租户 demo（主键 " in out and "主键 0" not in out, "主键来自 sys_tenant（非兜底 0）"
    assert "库名基 demo" in out, "库名基来自对照表"
    assert "platform → identity" in out, "源单元来自当前拓扑"
    assert "biz" in out, "依赖方来自能力授权表"


def test_plan_rejects_multi_unit_and_unmapped_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """拓扑不支撑的请求直接拒绝：多域分属不同单元、域不在拓扑里。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_platform(tmp_path))
    multi = ConcurrentStableList(
        ["--tenant", "demo", "--domain", "role", "--domain", "user", "--to-unit", "identity", "--step", "p1"]
    )
    assert migrate_topology.main(multi) == 1
    assert "多域当前分属不同单元" in capsys.readouterr().err

    unmapped = ConcurrentStableList(["--tenant", "demo", "--domain", "txn", "--to-unit", "identity", "--step", "p1"])
    assert migrate_topology.main(unmapped) == 1
    assert "当前拓扑没有这些业务域的映射" in capsys.readouterr().err


def test_precheck_reports_unreachable_target_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1 失败分支：目标库不可取、源库不可读（各自给出原因后即停）。"""
    _prepare(tmp_path, monkeypatch)

    async def _boom(target: object) -> bool:
        """替身：目标库探测抛错。

        Args:
            target: 目标（忽略）。

        Returns:
            bool: 不会返回。
        """
        del target
        raise OSError("连接被拒绝")

    monkeypatch.setattr(migrate_topology, "database_exists", _boom)
    assert migrate_topology.main(_args(tmp_path, "--step", "p1")) == 1
    out = capsys.readouterr().out
    assert "目标库可取" in out and "连接被拒绝" in out

    monkeypatch.undo()
    _prepare(tmp_path, monkeypatch)

    async def _rows_boom(url: str, metadata: object) -> ConcurrentStableDict[str, int]:
        """替身：行数统计抛错。

        Args:
            url: 连接串（忽略）。
            metadata: 元数据（忽略）。

        Returns:
            ConcurrentStableDict[str, int]: 不会返回。
        """
        del url, metadata
        raise OSError("源库不可读")

    monkeypatch.setattr(migrate_topology, "count_rows", _rows_boom)
    assert migrate_topology.main(_args(tmp_path, "--step", "p1")) == 1
    assert "源库不可读：OSError" in capsys.readouterr().out


def test_dual_strategy_skips_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dual` 档不停写：无需 `--notice`，P1 通过。"""
    _prepare(tmp_path, monkeypatch)
    args = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--domain",
            "role",
            "--from-unit",
            "platform",
            "--to-unit",
            "identity",
            "--db-basis",
            "demo",
            "--strategy",
            "dual",
            "--state-dir",
            str(tmp_path / "state"),
            "--dry-run",
        ]
    )
    assert migrate_topology.main(args) == 0
    out = capsys.readouterr().out
    assert "dual 档不停写，无需告知" in out


def test_build_schema_upgrades_domain_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P2：域清单有脚本时执行到 head（本仓租户链当前无脚本，以替身锁该分支）。"""
    _prepare(tmp_path, monkeypatch)
    upgraded: ConcurrentStableList[str] = ConcurrentStableList()

    def _fake_head(series: object) -> str:
        """替身：任何清单都有 head。

        Args:
            series: 清单（忽略）。

        Returns:
            str: 假 revision。
        """
        del series
        return "0001"

    def _fake_upgrade(series: object, url: str, *, schema: str = "") -> None:
        """替身：记录被执行的清单。

        Args:
            series: 清单。
            url: 连接串（忽略）。
            schema: 模式（忽略）。
        """
        del url, schema
        upgraded.add(str(getattr(series, "name", "")))

    monkeypatch.setattr(migrate_topology, "head_revision", _fake_head)
    monkeypatch.setattr(migrate_topology, "upgrade_series", _fake_upgrade)
    assert migrate_topology.main(_args(tmp_path, "--step", "p2")) == 0
    assert "结构清单到 head：role" in capsys.readouterr().out
    assert upgraded == ConcurrentStableList(["role:tenant"])


def test_copy_failure_stops_before_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P3 失败（目标缺表）即停：不进入切换，报告逐表失败原因。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_source(tmp_path))
    assert migrate_topology.main(_args(tmp_path, "--step", "p3", "--step", "p4")) == 1
    out = capsys.readouterr().out
    assert "P3/P4 未通过：不切换" in out
    assert "失败" in out


def test_run_switch_step_after_green_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """全程编排：P4 绿后进入 P5（切换动作以替身锁调用点）。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_source(tmp_path))

    async def _fake_switch(plan: object, args: object) -> migrate_topology.StepResult:
        """替身：跳过真实平台应用，返回通过结论。

        Args:
            plan: 迁移计划（忽略）。
            args: 参数（忽略）。

        Returns:
            StepResult: 通过结论。
        """
        del plan, args
        return migrate_topology.StepResult(key="p5", title="切换与发布", passed=True, detail="替身切换")

    monkeypatch.setattr(migrate_topology, "_switch", _fake_switch)
    args = _args(tmp_path, "--step", "p2", "--step", "p3", "--step", "p4", "--step", "p5")
    assert migrate_topology.main(args) == 0
    assert "替身切换" in capsys.readouterr().out


def test_cleanup_requires_backup_ref_then_drops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """清理：缺备份凭据拒绝删库；给了凭据才删旧库（破坏性操作前置校验）。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_source(tmp_path))
    assert migrate_topology.main(_args(tmp_path, "--step", "cleanup")) == 1
    assert "缺 --backup-ref" in capsys.readouterr().out
    assert (tmp_path / _SOURCE_DB).exists()

    assert migrate_topology.main(_args(tmp_path, "--step", "cleanup", "--backup-ref", "bkp-20261205")) == 0
    assert "已删除" in capsys.readouterr().out
    assert not (tmp_path / _SOURCE_DB).exists()


def test_dual_strategy_runs_single_round_when_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dual` 档：全绿即刻收敛（converge 1 轮），不对已通过的库反复回填。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_source(tmp_path))
    args = _args(
        tmp_path,
        "--strategy",
        "dual",
        "--converge-rounds",
        "1",
        "--step",
        "p2",
        "--step",
        "p3",
        "--step",
        "p4",
    )
    assert migrate_topology.main(args) == 0
    out = capsys.readouterr().out
    assert "第 1 轮" in out and "dual" in out


def test_tenant_ref_rejects_unknown_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """注册库可读但没有该编码：明确报错（不静默当默认拓扑）。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_platform(tmp_path))
    args = ConcurrentStableList(["--tenant", "ghost", "--domain", "role", "--to-unit", "identity", "--step", "p1"])
    assert migrate_topology.main(args) == 1
    assert "未在租户注册库登记" in capsys.readouterr().err


def test_topology_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """租户自身无拓扑行时回落默认拓扑（`--tenant-id` 显式给主键）。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_platform(tmp_path))
    args = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--tenant-id",
            "42",
            "--domain",
            "role",
            "--to-unit",
            "identity",
            "--notice",
            "已告知",
            "--state-dir",
            str(tmp_path / "state"),
            "--step",
            "p1",
        ]
    )
    assert migrate_topology.main(args) == 0
    out = capsys.readouterr().out
    assert "租户 demo（主键 42）" in out and "platform → identity" in out


def test_dependents_dedupe_across_domains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """同单元多域：同一消费方的能力授权去重后只列一次。"""
    _prepare(tmp_path, monkeypatch)
    asyncio.run(_seed_platform(tmp_path))
    args = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--domain",
            "role",
            "--domain",
            "permission_meta",
            "--to-unit",
            "identity",
            "--notice",
            "已告知",
            "--state-dir",
            str(tmp_path / "state"),
            "--step",
            "p1",
        ]
    )
    assert migrate_topology.main(args) == 0
    out = capsys.readouterr().out
    assert out.count("biz") == 1, "同一消费方只列一次"


def test_platform_reads_use_sync_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """平台库走同步方言（达梦路径）：拓扑读面仍可用（同步连接适配层）。"""
    _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(migrate_topology, "_platform_url", lambda: f"sqlite:///{tmp_path}/sync_platform.db")
    monkeypatch.setattr(migrate_topology, "is_sync_only_url", _always_sync)
    asyncio.run(apply_domains_schema(["platform_registry"], "platform", f"sqlite:///{tmp_path}/sync_platform.db"))
    engine = create_engine(f"sqlite:///{tmp_path}/sync_platform.db")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO sys_tenant_topology (id, tenant_id, domain_key, unit_key, topology_version, "
                "status, created_at, updated_at, version) VALUES "
                "(1, 0, 'role', 'platform', 1, 'enabled', "
                "'2026-10-30 00:00:00', '2026-10-30 00:00:00', 0)"
            )
    finally:
        engine.dispose()
    args = ConcurrentStableList(
        [
            "--tenant",
            "demo",
            "--tenant-id",
            "0",
            "--domain",
            "role",
            "--to-unit",
            "identity",
            "--db-basis",
            "demo",
            "--notice",
            "已告知",
            "--state-dir",
            str(tmp_path / "state"),
            "--step",
            "p1",
        ]
    )
    assert migrate_topology.main(args) == 0
    assert "platform → identity" in capsys.readouterr().out


def _always_sync(url: str) -> bool:
    """替身：所有连接串判为仅同步方言。

    Args:
        url: 连接串（忽略）。

    Returns:
        bool: 恒 True。
    """
    del url
    return True


def test_topology_unreadable_reports_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """拓扑表缺失：给出「平台库 / sys_tenant_topology」可读性结论（不进 P1 结论前即停）。"""
    _prepare(tmp_path, monkeypatch)
    args = ConcurrentStableList(
        ["--tenant", "demo", "--tenant-id", "0", "--domain", "role", "--to-unit", "identity", "--step", "p1"]
    )
    assert migrate_topology.main(args) == 1
    assert "当前拓扑不可读" in capsys.readouterr().err


async def test_topology_units_falls_back_to_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """拓扑读面：租户自身无行时回落默认拓扑（直击读面，不经命令行）。"""
    _prepare(tmp_path, monkeypatch)
    await _seed_platform(tmp_path)
    raw = await migrate_topology._topology_rows(42)  # pyright: ignore[reportPrivateUsage]
    assert not raw, f"42 号租户不应有拓扑行：{dict(raw)}"
    units = await migrate_topology._topology_units(42)  # pyright: ignore[reportPrivateUsage]
    assert dict(units) == {"role": "platform", "user": "identity", "permission_meta": "platform"}
