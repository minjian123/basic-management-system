"""事件契约快照 CLI 测试（Kiwi 2174 / 2250）：export / check / 兼容违规 / 缺件 / 漂移 / 解析失败 / 产品契约注入。"""

import json
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import EventContractError
from bms_core.events.contracts import EventContractRegistry
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
    assert event_contracts.main(ConcurrentStableList(["export", "--root", str(tmp_path), "--print"])) == 0
    assert event_contracts.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 0
    output = capsys.readouterr().out
    assert "事件契约快照已写入" in output
    assert "事件契约校验通过" in output


_PRODUCT_MODULE_SOURCE = """\
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.contracts import EventContract, EventContractRegistry, EventFieldSpec


def register_product_event_contracts(registry: EventContractRegistry) -> None:
    registry.register(
        EventContract(
            event_type="pur.order.created",
            description="采购订单创建",
            fields=ConcurrentStableDict({"order_id": EventFieldSpec(type="string", required=True)}),
        )
    )
"""

_NO_HOOK_MODULE_SOURCE = """\
VALUE = 1
"""


def _write_module(directory: Path, name: str, source: str) -> None:
    """把产品侧声明模块写入临时目录（供导入）。

    Args:
        directory: 模块目录。
        name: 模块文件名（不含后缀）。
        source: 模块源码。
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.py").write_text(source, encoding="utf-8")


@pytest.mark.kiwi_id(2250)
def test_load_product_contracts_registers_into_target_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """产品契约声明模块经 `--product-contracts` 入口注入指定注册表（产品侧自持契约）。"""
    module_dir = tmp_path / "prodmod"
    _write_module(module_dir, "prod_events", _PRODUCT_MODULE_SOURCE)
    monkeypatch.syspath_prepend(str(module_dir))  # pyright: ignore[reportUnknownMemberType]

    registry = EventContractRegistry()
    event_contracts.load_product_contracts(registry, "prod_events")
    assert [contract.event_type for contract in registry.contracts()] == ["pur.order.created"]


@pytest.mark.kiwi_id(2250)
def test_load_product_contracts_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """产品契约声明不可用即拒（fail-closed）：模块不可导入 / 模块缺登记入口。"""
    with pytest.raises(EventContractError, match="不可导入"):
        event_contracts.load_product_contracts(EventContractRegistry(), "no_such_product_module")

    module_dir = tmp_path / "nohook"
    _write_module(module_dir, "no_hook_events", _NO_HOOK_MODULE_SOURCE)
    monkeypatch.syspath_prepend(str(module_dir))  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(EventContractError, match="缺少 register_product_event_contracts"):
        event_contracts.load_product_contracts(EventContractRegistry(), "no_hook_events")


@pytest.mark.kiwi_id(2250)
def test_main_product_contracts_unavailable_exits_nonzero(tmp_path: Path) -> None:
    """CLI 带不可导入的产品契约模块时退出码 1（不静默降级）。"""
    assert (
        event_contracts.main(
            ConcurrentStableList(["check", "--root", str(tmp_path), "--product-contracts", "no.such.product.mod"])
        )
        == 1
    )
