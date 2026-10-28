"""发布 / 回滚 CLI 纯函数测试（Kiwi 2185）：台账轮转、回滚目标解析、SHA 标签清理、发布清单。

`scripts/tools/deploy/release.py` 以 importlib 直接加载（与 `test_render_alertmanager.py` 同模式），
只调用其纯函数——不触网、不调用 `docker`。
"""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "deploy" / "release.py"
_spec = importlib.util.spec_from_file_location("release_cli", _SCRIPT)
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


def _noop(*args: Any, **kwargs: Any) -> None:
    """占位替换（吞掉参数）。"""
    del args, kwargs


def _fail_check(*args: Any, **kwargs: Any) -> int:
    """对账恒失败（退出码 1）。"""
    del args, kwargs
    return 1


def _ok_deploy(*args: Any, **kwargs: Any) -> bool:
    """部署恒成功。"""
    del args, kwargs
    return True


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
    ledger: ConcurrentStableDict[str, Any] = ConcurrentStableDict(
        {
            "current": {"tag": "v0.3.0"},
            "previous": {"tag": "v0.2.0"},
        }
    )
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
    assert "人工确认" in str(manifest["checklist"]["schema_drill"])


@pytest.mark.kiwi_id(2185)
def test_gateway_check_args_and_volumes(tmp_path: Path) -> None:
    """注册表对账：容器内命令走 `--from-registry` + 只读根挂载（不向宿主传库凭据）。"""
    assert list(release.gateway_check_args()) == [
        "python",
        "-m",
        "ops.gateway_config",
        "check",
        "--from-registry",
        "--root",
        release.GATEWAY_CHECK_ROOT,
    ]
    assert list(release.gateway_check_volumes(tmp_path)) == [
        f"{tmp_path.resolve()}:{release.GATEWAY_CHECK_ROOT}/deploy:ro"
    ]


@pytest.mark.kiwi_id(2185)
def test_cmd_gateway_check_requires_platform_tag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """对账缺 platform 标签：退出码 2 且提示补标签（不猜版本）。"""
    assert release.cmd_gateway_check(tmp_path, ConcurrentStableDict({})) == 2
    assert "需 platform 镜像标签" in capsys.readouterr().err


@pytest.mark.kiwi_id(2185)
def test_cmd_gateway_check_passes_and_reports_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """对账透出容器退出码：0 报通过；非 0 报漂移与重生成指引。"""
    seen: ConcurrentStableList[Any] = ConcurrentStableList()

    def _run(deploy_dir: Path, env: ConcurrentStableDict[str, str], service: str, command: Any, **kwargs: Any) -> int:
        seen.add((service, list(command), dict(kwargs)))
        return 0

    monkeypatch.setattr(release, "_compose_run", _run)
    env: ConcurrentStableDict[str, str] = ConcurrentStableDict({"BMS_TAG_PLATFORM": "abc1234"})
    assert release.cmd_gateway_check(tmp_path, env) == 0
    assert "对账通过" in capsys.readouterr().out
    assert seen[0][0] == release.GATEWAY_CHECK_IMAGE
    assert seen[0][2]["raise_on_error"] is False

    monkeypatch.setattr(release, "_compose_run", _fail_check)
    assert release.cmd_gateway_check(tmp_path, env) == 1
    assert "对账未通过" in capsys.readouterr().err


@pytest.mark.kiwi_id(2185)
def test_cmd_deploy_aborts_when_gateway_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """对账失败即中止部署：不起任何容器，发布日志记 failure。"""
    monkeypatch.setattr(release, "_ensure_registry_login", _noop)
    monkeypatch.setattr(release, "cmd_gateway_check", _fail_check)
    deployed: ConcurrentStableList[Any] = ConcurrentStableList()

    def _deploy(*args: Any, **kwargs: Any) -> bool:
        """记录被调用的部署（不应发生）。"""
        del kwargs
        deployed.add(args)
        return True

    monkeypatch.setattr(release, "_deploy_one", _deploy)

    code = release.cmd_deploy(
        tmp_path,
        ConcurrentStableDict({"BMS_TAG_PLATFORM": "abc1234"}),
        services=ConcurrentStableList(["platform"]),
        tag="v0.2.0",
        actor="tester",
    )
    assert code == 1
    assert list(deployed) == []
    assert "中止部署" in capsys.readouterr().err
    log = (tmp_path / "releases" / "release-log.jsonl").read_text(encoding="utf-8")
    assert '"action": "gateway-check"' in log
    assert '"result": "failure"' in log


@pytest.mark.kiwi_id(2185)
def test_cmd_deploy_skip_gateway_check_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--skip-gateway-check`：不调对账、照常部署，日志记 skipped（留痕不静默）。"""

    def _no_check(*args: Any, **kwargs: Any) -> int:
        raise AssertionError("跳过对账时不应调用 cmd_gateway_check")

    monkeypatch.setattr(release, "_ensure_registry_login", _noop)
    monkeypatch.setattr(release, "cmd_gateway_check", _no_check)
    monkeypatch.setattr(release, "_deploy_one", _ok_deploy)

    code = release.cmd_deploy(
        tmp_path,
        ConcurrentStableDict({"BMS_TAG_PLATFORM": "abc1234"}),
        services=ConcurrentStableList(["platform"]),
        tag="v0.2.0",
        actor="tester",
        skip_gateway_check=True,
    )
    assert code == 0
    assert "跳过注册表对账" in capsys.readouterr().out
    log = (tmp_path / "releases" / "release-log.jsonl").read_text(encoding="utf-8")
    assert '"result": "skipped"' in log


@pytest.mark.kiwi_id(2185)
def test_cmd_seed_propagates_business_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """种子编排退出码原样透出（冲突 1 / 执行失败 2 / 前置错误 3），不吞成 0 或异常。"""
    seen: ConcurrentStableList[Any] = ConcurrentStableList()

    def _run(deploy_dir: Path, env: ConcurrentStableDict[str, str], service: str, command: Any, **kwargs: Any) -> int:
        seen.add((service, list(command), dict(kwargs)))
        return 2

    def _image(module: str) -> str:
        """种子编排镜像（platform）。"""
        del module
        return "platform"

    monkeypatch.setattr(release, "_run_image_of", _image)
    monkeypatch.setattr(release, "_compose_run", _run)

    code = release.cmd_seed(
        tmp_path, ConcurrentStableDict({"BMS_TAG_PLATFORM": "abc1234"}), tenant="demo", dry_run=False, actor="tester"
    )
    assert code == 2
    assert "退出码 2" in capsys.readouterr().err
    assert seen[0][0] == "platform"
    assert seen[0][1] == ["python", "-m", "ops.seed_platform", "--tenant", "demo"]
    assert seen[0][2]["raise_on_error"] is False
