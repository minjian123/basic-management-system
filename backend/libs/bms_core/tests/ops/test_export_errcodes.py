"""错误码手册导出 CLI：export / check / 格式与确定性（07B `02_05`）。

覆盖：md / json 渲染（列序、状态文案）、stdout 与 `--out` 两种落点、`check` 一致 / 不一致 /
缺文件、未配置清单时的提示，以及 `__main__` 守卫。

新增用例的 Kiwi 编号由 07B `05_01` 统一登记后回填（本批不标 `kiwi_id`）。
"""

# pyright: reportUnusedFunction=false
import json
import runpy
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.services.module_registry import (
    PLATFORM_ERROR_CODE_RECORDS,
    ErrorCodeRecord,
    register_error_code_records,
    reset_error_code_records,
)
from ops import export_errcodes


def _record(code: int = 390001) -> ErrorCodeRecord:
    """构造一条产品错误码记录。

    Args:
        code: 错误码。

    Returns:
        ErrorCodeRecord: 记录。
    """
    return ErrorCodeRecord(
        code=code,
        domain="org",
        http_status=404,
        message_key="demo.error.dept_not_found",
        severity="warning",
        description="部门不存在",
        product_key="demo",
        segment="39",
    )


def _settings(paths: ConcurrentStableList[str]) -> object:
    """构造配置替身（只含 `[registry].product_manifests`）。

    Args:
        paths: 清单路径。

    Returns:
        object: 配置替身。
    """
    return types.SimpleNamespace(registry=types.SimpleNamespace(product_manifests=paths))


@pytest.fixture(autouse=True)
def _isolate_records(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每例：清空注入记录 + 缺省视为「未配置清单」。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    reset_error_code_records()
    monkeypatch.setattr(export_errcodes, "get_settings", lambda: _settings(ConcurrentStableList(())))
    yield
    reset_error_code_records()


def test_render_markdown_columns_and_status() -> None:
    """md 渲染：表头列序固定、状态标注「启用」、行数 = 记录数。"""
    records = ConcurrentStableList((PLATFORM_ERROR_CODE_RECORDS[10002], _record()))
    text = export_errcodes.render_markdown(records)
    lines = text.splitlines()
    assert lines[0].startswith("| 错误码 | 段 | 业务域 | 提供方 | HTTP |")
    assert len(lines) == 2 + len(records)
    assert "| `390001` | 39 | org | demo | 404 | `demo.error.dept_not_found` | warning | 部门不存在 | 启用 |" in lines


def test_render_marks_disabled_records() -> None:
    """停用码：导出标注「已停用（码位保留不复用）」，仍出现在表中。"""
    record = ErrorCodeRecord(
        code=390002,
        domain="org",
        http_status=200,
        message_key="demo.error.dept_gone",
        severity="warning",
        description="部门已删除",
        product_key="demo",
        segment="39",
        status="disabled",
    )
    text = export_errcodes.render_markdown(ConcurrentStableList((record,)))
    assert "已停用（码位保留不复用）" in text


def test_render_json_is_deterministic_and_complete() -> None:
    """json 渲染：键排序、字段齐备、同输入同文本。"""
    records = ConcurrentStableList((_record(),))
    text = export_errcodes.render_json(records)
    assert text == export_errcodes.render_json(records)
    payload = json.loads(text)
    assert payload[0]["code"] == 390001
    assert set(payload[0]) == set(export_errcodes.COLUMNS)


def test_build_records_without_manifests_warns(capsys: pytest.CaptureFixture[str]) -> None:
    """未配置清单：只含平台码，并向 stderr 提示（不静默）。"""
    records = export_errcodes.build_records()
    assert len(records) == len(PLATFORM_ERROR_CODE_RECORDS)
    assert "未配置" in capsys.readouterr().err


def test_build_records_loads_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """配置清单：装载后产品码进入导出（与装配期同源）。"""
    path = tmp_path / "deploy" / "registry" / "demo.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """\
product_key = "demo"

[[products]]
product_key = "demo"
name = "演示产品"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
errcode_segment = "39"
event_domain = "demo"
service_group = "product"
product_key = "demo"

[[errcodes]]
code = 390001
domain = "org"
http_status = 404
message_key = "demo.error.dept_not_found"
severity = "warning"
description = "部门不存在"
""",
        encoding="utf-8",
    )
    contract = tmp_path / "deploy" / "contracts" / "demo.json"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text(json.dumps({"paths": {"/api/v1/demo/depts": {}}}), encoding="utf-8")
    monkeypatch.setattr(export_errcodes, "get_settings", lambda: _settings(ConcurrentStableList((str(path),))))
    records = export_errcodes.build_records()
    assert any(record.code == 390001 for record in records)


def test_export_stdout_and_out_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """export：缺省打印 stdout；`--out` 落文件且内容一致。"""
    assert export_errcodes.main(ConcurrentStableList(("export",))) == 0
    assert "| 错误码 |" in capsys.readouterr().out
    target = tmp_path / "errcodes.md"
    assert export_errcodes.main(ConcurrentStableList(("export", "--out", str(target)))) == 0
    assert target.is_file()
    assert "| 错误码 |" in target.read_text(encoding="utf-8")


def test_check_roundtrip_and_drift(tmp_path: Path) -> None:
    """check：导出文件一致通过（0）；篡改后不一致（1）；md 与 json 两种格式各自比对。"""
    md_path = tmp_path / "errcodes.md"
    json_path = tmp_path / "errcodes.json"
    assert export_errcodes.main(ConcurrentStableList(("export", "--out", str(md_path)))) == 0
    assert export_errcodes.main(ConcurrentStableList(("export", "--format", "json", "--out", str(json_path)))) == 0
    assert export_errcodes.main(ConcurrentStableList(("check", str(md_path)))) == 0
    assert export_errcodes.main(ConcurrentStableList(("check", str(json_path), "--format", "json"))) == 0
    md_path.write_text("tampered", encoding="utf-8")
    assert export_errcodes.main(ConcurrentStableList(("check", str(md_path)))) == 1
    json_path.write_text("[]", encoding="utf-8")
    assert export_errcodes.main(ConcurrentStableList(("check", str(json_path), "--format", "json"))) == 1


def test_check_missing_file_fails(tmp_path: Path) -> None:
    """check：未给路径 / 路径不存在均以退出码 1 收口。"""
    assert export_errcodes.main(ConcurrentStableList(("check",))) == 1
    assert export_errcodes.main(ConcurrentStableList(("check", str(tmp_path / "absent.md")))) == 1


def test_json_check_ignores_formatting(tmp_path: Path) -> None:
    """json check 按结构比对：重排格式仍视为一致。"""
    target = tmp_path / "errcodes.json"
    assert export_errcodes.main(ConcurrentStableList(("export", "--format", "json", "--out", str(target)))) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    target.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    assert export_errcodes.main(ConcurrentStableList(("check", str(target), "--format", "json"))) == 0


def test_module_main_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ops.export_errcodes` 入口（__main__ 守卫）可执行。"""
    target = tmp_path / "errcodes.md"
    monkeypatch.setattr(sys, "argv", ["export_errcodes", "export", "--out", str(target)])
    monkeypatch.delitem(sys.modules, "ops.export_errcodes", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("ops.export_errcodes", run_name="__main__")
    assert excinfo.value.code == 0


def test_register_records_visible_in_export() -> None:
    """直接注册的记录（不经清单）也进入导出（视图为唯一来源）。"""
    register_error_code_records(ConcurrentStableList((_record(390051),)))
    records = export_errcodes.build_records()
    assert [record.code for record in records][-1] == 390051
