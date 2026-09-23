"""事件契约快照 CLI 测试（Kiwi 2174）：export / check / 兼容违规 / 缺件 / 漂移 / 解析失败。"""

import json
from pathlib import Path

import pytest

from ops import event_contracts


@pytest.mark.kiwi_id(2174)
def test_export_and_check_roundtrip(tmp_path: Path) -> None:
    """export 写出快照、check 零漂移通过；无快照时 export 直接成功（首跑）。"""
    assert event_contracts.export(tmp_path) == 0
    assert event_contracts.snapshot_path(tmp_path).is_file()
    assert event_contracts.check(tmp_path) == 0


@pytest.mark.kiwi_id(2174)
def test_check_missing_snapshot_fails(tmp_path: Path) -> None:
    """快照缺件时 check 退出码 1。"""
    assert event_contracts.check(tmp_path) == 1


@pytest.mark.kiwi_id(2174)
def test_check_drift_fails(tmp_path: Path) -> None:
    """快照被篡改（版本漂移）时 check 退出码 1。"""
    assert event_contracts.export(tmp_path) == 0
    path = event_contracts.snapshot_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["contracts"][0]["version"] = "9.9.9"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert event_contracts.check(tmp_path) == 1


@pytest.mark.kiwi_id(2174)
def test_export_rejects_incompatible_change(tmp_path: Path) -> None:
    """快照含现行注册表已删除的字段（破坏性）→ export 退出 1 且不改写快照。"""
    assert event_contracts.export(tmp_path) == 0
    path = event_contracts.snapshot_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["contracts"][0]["fields"]["ghost_field"] = {"required": True, "type": "string"}
    tampered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(tampered, encoding="utf-8")
    assert event_contracts.export(tmp_path) == 1
    assert path.read_text(encoding="utf-8") == tampered


@pytest.mark.kiwi_id(2174)
def test_check_and_export_invalid_snapshot_fails(tmp_path: Path) -> None:
    """已提交快照不可解析（JSON 非法）时 check / export 均退出 1。"""
    path = event_contracts.snapshot_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    assert event_contracts.check(tmp_path) == 1
    assert event_contracts.export(tmp_path) == 1


@pytest.mark.kiwi_id(2174)
def test_main_dispatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """命令行分发：export（--print）/ check。"""
    assert event_contracts.main(["export", "--root", str(tmp_path), "--print"]) == 0
    assert event_contracts.main(["check", "--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "事件契约快照已写入" in output
    assert "事件契约校验通过" in output
