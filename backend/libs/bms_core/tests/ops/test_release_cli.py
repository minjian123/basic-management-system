"""发布 / 回滚 CLI 纯函数测试（Kiwi 2185）：台账轮转、回滚目标解析、SHA 标签清理、发布清单。

`scripts/tools/deploy/release.py` 以 importlib 直接加载（与 `test_render_alertmanager.py` 同模式），
只调用其纯函数——不触网、不调用 `docker`。
"""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "deploy" / "release.py"
_spec = importlib.util.spec_from_file_location("release_cli", _SCRIPT)
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


@pytest.mark.kiwi_id(2185)
def test_parse_env_ignores_comments_and_quotes() -> None:
    """`.env` 解析：忽略注释 / 空行、去引号、支持 export 前缀。"""
    text = "# 注释\n\nPLAIN=value\nQUOTED=\"a=b#c\"\nSINGLE='x'\nexport EXPORTED=yes\nEMPTY=\n"
    parsed = release.parse_env(text)
    assert parsed["PLAIN"] == "value"
    assert parsed["QUOTED"] == "a=b#c"
    assert parsed["SINGLE"] == "x"
    assert parsed["EXPORTED"] == "yes"
    assert parsed["EMPTY"] == ""


@pytest.mark.kiwi_id(2185)
def test_is_semver() -> None:
    """语义化版本识别（`vX.Y.Z`；SHA 与裸版本不算）。"""
    assert release.is_semver("v1.2.3")
    assert not release.is_semver("1.2.3")
    assert not release.is_semver("07947c1b")
    assert not release.is_semver("latest")


@pytest.mark.kiwi_id(2185)
def test_rotate_ledger_first_and_second_deploy() -> None:
    """台账轮转：首次部署无上一版本；再次部署把原 current 转为 previous。"""
    first = release.rotate_ledger({"service": "platform"}, tag="abc1234", actor="mj", at="t1")
    assert first["current"]["tag"] == "abc1234"
    assert first["previous"] is None
    second = release.rotate_ledger(first, tag="v0.2.0", actor="mj", at="t2")
    assert second["current"]["tag"] == "v0.2.0"
    assert second["previous"]["tag"] == "abc1234"
    # 入参不被修改
    assert first["current"]["tag"] == "abc1234"


@pytest.mark.kiwi_id(2185)
def test_resolve_rollback_target() -> None:
    """回滚目标解析：`--to` 优先；缺省上一版本；无上一版本报错。"""
    ledger: dict[str, Any] = {
        "current": {"tag": "v0.3.0"},
        "previous": {"tag": "v0.2.0"},
    }
    assert release.resolve_rollback_target(ledger, "v0.1.0") == "v0.1.0"
    assert release.resolve_rollback_target(ledger) == "v0.2.0"
    with pytest.raises(ValueError):
        release.resolve_rollback_target({"service": "platform"})


@pytest.mark.kiwi_id(2185)
def test_select_prunable_tags_keeps_semver_and_recent_sha() -> None:
    """清理选择：semver 永久保留；SHA 保留最近 N（按推送时间倒序）。"""
    tags = [
        {"name": "v0.1.0", "created_at": "2026-01-01T00:00:00Z"},
        {"name": "aaa1111", "created_at": "2026-01-05T00:00:00Z"},
        {"name": "bbb2222", "created_at": "2026-01-04T00:00:00Z"},
        {"name": "ccc3333", "created_at": "2026-01-03T00:00:00Z"},
    ]
    assert release.select_prunable_tags(tags, 2) == ["ccc3333"]
    assert release.select_prunable_tags(tags, 0) == []
    assert release.select_prunable_tags(tags, 5) == []


@pytest.mark.kiwi_id(2185)
def test_build_manifest_fields_and_placeholders() -> None:
    """发布清单：可采集项填充，不可采集检查项以「人工确认」占位。"""
    manifest = release.build_manifest(
        service="platform",
        commit="fullsha",
        short_sha="abc1234",
        image="registry/bms-platform:abc1234",
        digest="sha256:deadbeef",
        scan="pass",
        pipeline_url="http://gitlab/pipelines/1",
        tag="v0.2.0",
        built_at="2026-09-24T00:00:00Z",
    )
    assert manifest["service"] == "platform"
    assert manifest["tag"] == "v0.2.0"
    assert manifest["digest"] == "sha256:deadbeef"
    assert manifest["checklist"]["image_scan"] == "pass"
    assert "人工确认" in str(manifest["checklist"]["migration_drill"])
