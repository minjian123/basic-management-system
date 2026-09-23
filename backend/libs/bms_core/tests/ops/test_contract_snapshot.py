"""公开契约快照 CLI 测试（Kiwi 2168）：export / check 零漂移 / 缺件 / 多余件 / 漂移。"""

import runpy
import sys
import types
from pathlib import Path

import pytest

from bms_core.services.service_contract import contract_file_name, enabled_service_records, render_contract_json
from ops import contract_snapshot


def _first_service_key() -> str:
    """取首个启用服务标识。"""
    return str(enabled_service_records()[0].service_key)


@pytest.mark.kiwi_id(2168)
def test_export_and_check_roundtrip(tmp_path: Path) -> None:
    """export 写出各启用服务快照，check 零漂移通过。"""
    assert contract_snapshot.export(tmp_path) == 0
    for record in enabled_service_records():
        path = contract_snapshot.snapshot_path(tmp_path, str(record.service_key))
        assert path.is_file()
        assert path.read_text(encoding="utf-8") == render_contract_json(
            contract_snapshot.build_openapi(str(record.service_key))
        )
    assert contract_snapshot.check(tmp_path) == 0


@pytest.mark.kiwi_id(2168)
def test_check_missing_files_fails(tmp_path: Path) -> None:
    """快照目录缺失 / 缺件时 check 退出码非 0。"""
    assert contract_snapshot.check(tmp_path) == 1


@pytest.mark.kiwi_id(2168)
def test_check_extra_file_fails(tmp_path: Path) -> None:
    """存在多余快照文件时 check 退出码非 0。"""
    assert contract_snapshot.export(tmp_path) == 0
    (contract_snapshot.contracts_dir(tmp_path) / "ghost.json").write_text("{}\n", encoding="utf-8")
    assert contract_snapshot.check(tmp_path) == 1


@pytest.mark.kiwi_id(2168)
def test_check_drift_fails(tmp_path: Path) -> None:
    """快照被篡改（与公开契约漂移）时 check 退出码非 0。"""
    assert contract_snapshot.export(tmp_path) == 0
    target = contract_snapshot.snapshot_path(tmp_path, _first_service_key())
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert contract_snapshot.check(tmp_path) == 1


@pytest.mark.kiwi_id(2168)
def test_committed_snapshots_in_sync() -> None:
    """仓库内 deploy/contracts 快照与各服务公开契约零漂移。"""
    assert contract_snapshot.check(contract_snapshot.REPO_ROOT) == 0


@pytest.mark.kiwi_id(2168)
def test_module_main_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ops.contract_snapshot` 入口（__main__ 守卫）可执行。"""
    assert contract_snapshot.export(tmp_path) == 0
    monkeypatch.setattr(sys, "argv", ["contract_snapshot", "check", "--root", str(tmp_path)])
    monkeypatch.delitem(sys.modules, "ops.contract_snapshot", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("ops.contract_snapshot", run_name="__main__")
    assert excinfo.value.code == 0


@pytest.mark.kiwi_id(2168)
def test_contract_file_name_used() -> None:
    """快照文件名与契约工具同源。"""
    assert contract_snapshot.snapshot_path(Path("."), "platform").name == contract_file_name("platform")


@pytest.mark.kiwi_id(2168)
def test_export_print_and_main_subcommands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """export --print 打印内容；main 子命令 export / check 可执行。"""
    assert contract_snapshot.main(["export", "--print", "--root", str(tmp_path)]) == 0
    assert "info" in capsys.readouterr().out
    assert contract_snapshot.main(["check", "--root", str(tmp_path)]) == 0


@pytest.mark.kiwi_id(2168)
def test_build_openapi_missing_service() -> None:
    """目标服务包缺失时构建报错。"""
    with pytest.raises(RuntimeError, match="服务包缺失"):
        contract_snapshot.build_openapi("ghost")


@pytest.mark.kiwi_id(2168)
def test_build_openapi_missing_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务模块缺少 ApplicationFactory 时构建报错。"""
    module = types.ModuleType("bms_probe.main")

    def fake_import(name: str, package: str | None = None) -> types.ModuleType:
        del name, package
        return module

    monkeypatch.setattr(contract_snapshot, "import_module", fake_import)
    with pytest.raises(RuntimeError, match="缺少 ApplicationFactory"):
        contract_snapshot.build_openapi("probe")


@pytest.mark.kiwi_id(2168)
def test_build_openapi_build_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用构建失败时统一报服务名。"""
    module = types.ModuleType("bms_probe.main")
    setattr(module, "ApplicationFactory", object)  # noqa: B010 - 动态注入测试替身

    def fake_import(name: str, package: str | None = None) -> types.ModuleType:
        del name, package
        return module

    monkeypatch.setattr(contract_snapshot, "import_module", fake_import)
    with pytest.raises(RuntimeError, match="服务应用构建失败"):
        contract_snapshot.build_openapi("probe")


@pytest.mark.kiwi_id(2168)
def test_export_and_check_validation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """快照校验失败：export / check 均以退出码 1 收口。"""
    assert contract_snapshot.export(tmp_path) == 0

    def fake_validate(record: object, openapi: object) -> list[str]:
        del record, openapi
        return ["版本不一致"]

    monkeypatch.setattr(contract_snapshot, "_validate", fake_validate)
    assert contract_snapshot.export(tmp_path) == 1
    assert contract_snapshot.check(tmp_path) == 1
