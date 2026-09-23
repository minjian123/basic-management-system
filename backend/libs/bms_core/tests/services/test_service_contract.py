"""服务公开契约工具测试（Kiwi 2168）：启用服务枚举 / 确定性渲染 / 契约校验。"""

import json

import pytest

from bms_core.services.service_contract import (
    contract_file_name,
    enabled_service_records,
    render_contract_json,
    service_enabled,
    validate_contract,
)


@pytest.mark.kiwi_id(2168)
def test_contract_file_name() -> None:
    """快照文件名由服务标识派生。"""
    assert contract_file_name("platform") == "platform.json"


@pytest.mark.kiwi_id(2168)
def test_enabled_services_and_lookup() -> None:
    """启用服务枚举只含 service_key 非空且启用的行；planned 服务不可用。"""
    records = enabled_service_records()
    keys = {record.service_key for record in records}
    assert "platform" in keys and "identity" in keys
    assert "workflow" not in keys  # planned
    assert service_enabled("platform") is True
    assert service_enabled("workflow") is False
    assert service_enabled("ghost") is False


@pytest.mark.kiwi_id(2168)
def test_render_contract_deterministic() -> None:
    """渲染确定性：键序无关，产出同一文本。"""
    first = render_contract_json({"b": 1, "a": {"y": 2, "x": 3}})
    second = render_contract_json({"a": {"x": 3, "y": 2}, "b": 1})
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == {"a": {"x": 3, "y": 2}, "b": 1}


@pytest.mark.kiwi_id(2168)
def test_validate_contract() -> None:
    """契约校验：版本一致 / 结构齐备通过；版本不符 / 结构缺失报错。"""
    record = enabled_service_records()[0]
    good: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "服务", "version": record.contract_version},
        "paths": {"/api/v1/x": {}},
    }
    assert validate_contract("platform", good, record) == []

    bad_version: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "服务", "version": "9.9.9"},
        "paths": {"/api/v1/x": {}},
    }
    errors = validate_contract("platform", bad_version, record)
    assert any("契约版本不一致" in message for message in errors)

    missing: dict[str, object] = {"openapi": "3.1.0", "info": {"title": "", "version": record.contract_version}}
    errors = validate_contract("platform", missing, record)
    assert any("paths 为空" in message for message in errors)
    assert any("title 为空" in message for message in errors)

    empty: dict[str, object] = {}
    errors = validate_contract("platform", empty, record)
    assert any("缺少 openapi 版本字段" in message for message in errors)
    assert any("缺少 info 段" in message for message in errors)
    assert any("paths 为空" in message for message in errors)
