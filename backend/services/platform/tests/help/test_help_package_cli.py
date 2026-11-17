"""帮助包命令行测试：参数默认值 / checksum / 编排 / 退出码（08_03）。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportArgumentType=false, reportDeprecated=false, reportAttributeAccessIssue=false

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import HelpPackageInvalidError
from bms_core.help.anchors import HelpAnchorKind
from bms_core.repositories.help_anchor import HelpAnchorEntry
from bms_core.tenant.registry import TenantRef
from bms_core.testing.namespace import Namespace
from bms_platform.domains.help import cli
from bms_platform.domains.help.cli import build_parser, main
from bms_platform.domains.help.services.package import (
    HelpLoadCounts,
    HelpLoadOutcome,
    HelpUnloadCounts,
    HelpUnloadOutcome,
)

from ._support import anchor_map, write_package

pytestmark = pytest.mark.kiwi_id(2522)


class _FakeSession:
    """假会话：只提供 `begin()`（装载 / 卸载写路径的事务上下文）。"""

    def begin(self) -> object:
        """返回一个空异步上下文。

        Returns:
            object: 异步上下文管理器。
        """

        @asynccontextmanager
        async def _noop() -> AsyncIterator[None]:
            yield None

        return _noop()


class _FakeService:
    """假装载服务：按预设结果返回，避免 CLI 编排用例连库。"""

    load_result: HelpLoadOutcome | None = None
    unload_result: HelpUnloadOutcome | None = None

    def __init__(self, session: object) -> None:
        self.session = session

    async def load(self, spec: object, *, anchors: object, apply: bool, lenient: bool) -> HelpLoadOutcome:
        assert self.load_result is not None
        return self.load_result

    async def unload(self, product_key: str, *, apply: bool) -> HelpUnloadOutcome:
        assert self.unload_result is not None
        return self.unload_result


def _load_args(tmp_path: Path, ns: Namespace, *extra: str):
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    return build_parser().parse_args(["load", "--package", str(package), "--tenant", "demo", *extra])


def test_parser_defaults_to_dry_run_and_strict() -> None:
    """装载 / 卸载缺省 dry-run，严格模式缺省。"""
    args = build_parser().parse_args(["load", "--package", "help/package.yaml", "--tenant", "demo"])
    assert args.apply is False
    assert args.lenient is False
    unload = build_parser().parse_args(["unload", "--product", "bms", "--tenant", "demo"])
    assert unload.apply is False


def test_checksum_command_prints_and_writes(tmp_path: Path, ns: Namespace, capsys: pytest.CaptureFixture[str]) -> None:
    """checksum 子命令可打印并回写。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    assert main(["checksum", "--package", str(package)]) == 0
    printed = capsys.readouterr().out.strip()
    assert printed.startswith("sha256:")
    raw = package.read_text(encoding="utf-8")
    package.write_text(
        "\n".join(line for line in raw.splitlines() if not line.startswith("checksum:")), encoding="utf-8"
    )
    assert main(["checksum", "--package", str(package), "--write"]) == 0
    assert "checksum: sha256:" in package.read_text(encoding="utf-8")


def test_missing_target_exits_64(ns: Namespace, tmp_path: Path) -> None:
    """既不给 --tenant 也不给 --all-tenants 时参数错误。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    with pytest.raises(SystemExit) as exc:
        main(["load", "--package", str(package)])
    assert exc.value.code == 64


def test_main_maps_business_and_runtime_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """top-level 异常映射：业务拒收 1 / 执行错误 2。"""

    def _raise_biz(args: object) -> int:
        raise HelpPackageInvalidError("bad")

    monkeypatch.setattr(cli, "_run_checksum", _raise_biz)
    assert main(["checksum", "--package", "x"]) == 1

    def _raise_db(args: object) -> int:
        raise OperationalError("select 1", {}, Exception("boom"))

    monkeypatch.setattr(cli, "_run_checksum", _raise_db)
    assert main(["checksum", "--package", "x"]) == 2


def test_print_and_json_helpers(ns: Namespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """输出 / JSON 结构覆盖成功与失败占位结果。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = cli.load_package(package)
    outcome = HelpLoadOutcome(
        counts=HelpLoadCounts(articles_new=1, articles_skipped_override=1),
        package_action="created",
        warnings=ConcurrentStableFrozenList(("warn",)),
        applied=False,
    )
    results = ConcurrentStableList([("demo", outcome), ("acme", cli._failed_load("boom"))])
    cli._print_load(results, spec=spec, applied=False)
    assert "预演" in capsys.readouterr().out
    payload = cli._load_json(results)
    assert isinstance(payload, list) and payload[0]["tenant"] == "demo"

    unload = ConcurrentStableList(
        [
            ("demo", HelpUnloadOutcome(counts=HelpUnloadCounts(articles_offline=1), applied=True)),
            ("acme", cli._failed_unload("x")),
        ]
    )
    cli._print_unload(unload, product=ns.prefix, applied=True)
    assert "执行" in capsys.readouterr().out
    assert isinstance(cli._unload_json(unload), list)
    assert cli._exit_code(refused=True, failed=False) == 1
    assert cli._exit_code(refused=False, failed=True) == 2
    assert cli._exit_code(refused=False, failed=False) == 0


def test_tenant_and_anchor_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户解析（全部 / 显式 / 未知回落）与锚点归集。"""
    refs = ConcurrentStableList(
        [TenantRef(code="demo", db_basis="demo"), TenantRef(code="acme", db_basis="acme_basis")]
    )

    async def _tenant_refs(url: str) -> ConcurrentStableList[TenantRef]:
        assert url == "sqlite+aiosqlite://"
        return refs

    class _Factory:
        def resolved_url(self, key: str) -> str:
            assert key.startswith("platform_")
            return "sqlite+aiosqlite://"

    monkeypatch.setattr(cli, "tenant_refs", _tenant_refs)
    factory = _Factory()
    assert len(asyncio.run(cli._resolve_tenants(factory, ConcurrentStableList(), True))) == 2
    chosen = asyncio.run(cli._resolve_tenants(factory, ConcurrentStableList(["demo", "ghost"]), False))
    assert chosen[0].db_basis == "demo"
    assert chosen[1].db_basis == "ghost"

    entries = ConcurrentStableList(
        [HelpAnchorEntry(kind=HelpAnchorKind.MENU, table="sys_menu", model_id=1, help_key="platform:x:::")]
    )

    async def _list_anchors(session: object) -> ConcurrentStableList[HelpAnchorEntry]:
        return entries

    @asynccontextmanager
    async def _scope(registry: object, db_key: str, read_only: bool = False) -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(cli, "list_help_anchors", _list_anchors)
    monkeypatch.setattr(cli, "session_scope", _scope)
    anchors = asyncio.run(cli._load_anchors(object()))
    assert anchors["platform:x:::"] == HelpAnchorKind.MENU


def test_load_and_unload_for_tenant_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ns: Namespace) -> None:
    """单租户装载 / 卸载的实跑与预演分支。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = cli.load_package(package)
    _FakeService.load_result = HelpLoadOutcome(counts=HelpLoadCounts(articles_new=1), package_action="created")
    _FakeService.unload_result = HelpUnloadOutcome(counts=HelpUnloadCounts(articles_offline=1))
    monkeypatch.setattr(cli, "HelpPackageService", _FakeService)

    @asynccontextmanager
    async def _scope(registry: object, db_key: str, read_only: bool = False) -> AsyncIterator[object]:
        yield _FakeSession()

    monkeypatch.setattr(cli, "session_scope", _scope)
    applied = asyncio.run(
        cli._load_for_tenant(object(), "tenant_demo", spec, anchors=anchor_map(ns.prefix), apply=True, lenient=False)
    )
    dry = asyncio.run(
        cli._load_for_tenant(object(), "tenant_demo", spec, anchors=anchor_map(ns.prefix), apply=False, lenient=False)
    )
    assert applied.counts.articles_new == 1 and dry.applied is False
    unloaded = asyncio.run(cli._unload_for_tenant(object(), "tenant_demo", ns.prefix, apply=True))
    preview = asyncio.run(cli._unload_for_tenant(object(), "tenant_demo", ns.prefix, apply=False))
    assert unloaded.counts.articles_offline == 1 and preview.applied is False


def test_run_load_and_unload_orchestration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ns: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """多租户编排：成功 / 业务拒收 / 执行错误 / JSON 输出。"""
    args = _load_args(tmp_path, ns)
    refs = ConcurrentStableList([TenantRef(code="demo", db_basis="demo")])

    async def _resolve(factory: object, codes: object, all_tenants: bool) -> ConcurrentStableList[TenantRef]:
        return refs

    async def _anchors(registry: object) -> ConcurrentStableDict[str, HelpAnchorKind]:
        return anchor_map(ns.prefix)

    async def _ok(
        registry: object, db_key: str, spec: object, *, anchors: object, apply: bool, lenient: bool
    ) -> HelpLoadOutcome:
        return HelpLoadOutcome(counts=HelpLoadCounts(articles_new=1), package_action="created")

    monkeypatch.setattr(cli, "_resolve_tenants", _resolve)
    monkeypatch.setattr(cli, "_load_anchors", _anchors)
    monkeypatch.setattr(cli, "_load_for_tenant", _ok)
    assert asyncio.run(cli._run_load(args, object(), object())) == 0
    assert "新增 1" in capsys.readouterr().out
    args.json = True
    assert asyncio.run(cli._run_load(args, object(), object())) == 0
    assert '"tenant": "demo"' in capsys.readouterr().out

    async def _refuse(
        registry: object, db_key: str, spec: object, *, anchors: object, apply: bool, lenient: bool
    ) -> HelpLoadOutcome:
        raise HelpPackageInvalidError("bad")

    monkeypatch.setattr(cli, "_load_for_tenant", _refuse)
    assert asyncio.run(cli._run_load(args, object(), object())) == 1

    async def _fail(
        registry: object, db_key: str, spec: object, *, anchors: object, apply: bool, lenient: bool
    ) -> HelpLoadOutcome:
        raise OperationalError("select 1", {}, Exception("boom"))

    monkeypatch.setattr(cli, "_load_for_tenant", _fail)
    assert asyncio.run(cli._run_load(args, object(), object())) == 2

    unload_args = build_parser().parse_args(["unload", "--product", ns.prefix, "--all-tenants"])

    async def _unload_ok(registry: object, db_key: str, product_key: str, *, apply: bool) -> HelpUnloadOutcome:
        return HelpUnloadOutcome(counts=HelpUnloadCounts(articles_offline=1))

    monkeypatch.setattr(cli, "_unload_for_tenant", _unload_ok)
    assert asyncio.run(cli._run_unload(unload_args, object(), object())) == 0
    assert "下线文章 1" in capsys.readouterr().out

    async def _unload_refuse(registry: object, db_key: str, product_key: str, *, apply: bool) -> HelpUnloadOutcome:
        raise HelpPackageInvalidError("bad")

    monkeypatch.setattr(cli, "_unload_for_tenant", _unload_refuse)
    assert asyncio.run(cli._run_unload(unload_args, object(), object())) == 1

    async def _unload_fail(registry: object, db_key: str, product_key: str, *, apply: bool) -> HelpUnloadOutcome:
        raise OperationalError("select 1", {}, Exception("boom"))

    monkeypatch.setattr(cli, "_unload_for_tenant", _unload_fail)
    assert asyncio.run(cli._run_unload(unload_args, object(), object())) == 2
