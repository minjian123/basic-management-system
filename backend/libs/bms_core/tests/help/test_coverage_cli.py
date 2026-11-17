"""帮助覆盖率命令行（08_04；Kiwi 2523）。

被测对象：`bms_core/help/coverage_cli.py` 与 `ops/help_coverage.py` 的入口契约。数据库读取以桩快照替换，
只验证参数、退出码、豁免 / 基线与输出行为。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.help import coverage_cli
from bms_core.help.coverage import (
    HelpCoverageAction,
    HelpCoverageExemption,
    HelpCoverageExemptionSet,
    HelpCoverageModule,
    HelpCoverageScope,
    HelpCoverageSnapshot,
    build_help_coverage_ledger,
    ledger_payload,
)

AS_OF = date(2026, 11, 17)


def _argv(*items: str) -> ConcurrentStableList[str]:
    """构造命令行参数序列（与 `main` 的集合声明一致）。

    Args:
        items: 参数项。

    Returns:
        ConcurrentStableList[str]: 参数序列。
    """
    result: ConcurrentStableList[str] = ConcurrentStableList()
    for item in items:
        result.add(item)
    return result


def _snapshot(*, help_key: str | None = None) -> HelpCoverageSnapshot:
    """构造最小快照。

    Args:
        help_key: 动作锚点（None = 缺口）。

    Returns:
        HelpCoverageSnapshot: 快照。
    """
    return HelpCoverageSnapshot(
        actions=ConcurrentStableFrozenList(
            (
                HelpCoverageAction(
                    model_id=1,
                    business_code="user",
                    action_code="create",
                    button_name="新增",
                    menu_paths=ConcurrentStableFrozenList(("/sys/users",)),
                    help_key=help_key,
                    fallback_help_key=None,
                ),
            )
        ),
        menus=ConcurrentStableFrozenList(),
        modules=ConcurrentStableFrozenList(
            (HelpCoverageModule(business_code="user", product_key="platform", module_key="user", registered=True),)
        ),
        reference_rows=ConcurrentStableFrozenList(),
        action_fallbacks=ConcurrentStableFrozenList(),
        anchors=ConcurrentStableFrozenList(),
        business_codes_with_permission=ConcurrentStableFrozenList(("user",)),
    )


@pytest.fixture(autouse=True)
def _patch_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """把库解析与快照读取替换为内存桩。

    Args:
        monkeypatch: pytest monkeypatch。
    """

    async def fake_snapshot(_session: object) -> HelpCoverageSnapshot:
        return _snapshot()

    def fake_resolve(_url: str, *, service: str) -> str:
        del service
        return "sqlite+aiosqlite://"

    monkeypatch.setattr(coverage_cli, "resolve_url", fake_resolve)
    monkeypatch.setattr(coverage_cli, "load_help_coverage_snapshot", fake_snapshot)


@pytest.mark.kiwi_id(2523)
def test_parser_defaults() -> None:
    """参数缺省值符合告警档契约。"""
    args = coverage_cli.build_parser().parse_args([])
    assert args.format == "text"
    assert args.strict is False
    assert args.include_covered is False
    assert args.exemptions == []
    assert args.product_key == []


@pytest.mark.kiwi_id(2523)
def test_default_warning_and_strict_blocking(capsys: pytest.CaptureFixture[str]) -> None:
    """默认有缺口退出 0；--strict 退出 1；豁免后强档退出 0。"""
    assert coverage_cli.main(_argv("--as-of", "2026-11-17")) == 0
    assert "缺口 1" in capsys.readouterr().out

    assert coverage_cli.main(_argv("--as-of", "2026-11-17", "--strict")) == 1


@pytest.mark.kiwi_id(2523)
def test_exemption_file_makes_strict_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """限期豁免覆盖唯一缺口后强档通过。"""
    path = tmp_path / "exemptions.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exemptions": [
                    {
                        "kind": "action",
                        "key": "user:create",
                        "owner": "08_04",
                        "reason": "测试用的豁免理由不少于十个字",
                        "expires_at": "2027-03-31",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert coverage_cli.main(_argv("--as-of", "2026-11-17", "--strict", "--exemptions", str(path))) == 0
    assert "生效 1" in capsys.readouterr().out


@pytest.mark.kiwi_id(2523)
def test_output_and_baseline(tmp_path: Path) -> None:
    """--format json / --output 写文件；--baseline 输出对比。"""
    baseline_ledger = build_help_coverage_ledger(
        _snapshot(help_key="platform:user:user::create"),
        as_of=AS_OF,
        scope=HelpCoverageScope(
            product_keys=ConcurrentStableFrozenList(),
            module_keys=ConcurrentStableFrozenList(),
            kinds=ConcurrentStableFrozenList(),
            include_covered=True,
        ),
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(ledger_payload(baseline_ledger), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out" / "ledger.json"
    assert (
        coverage_cli.main(
            _argv(
                "--as-of",
                "2026-11-17",
                "--format",
                "json",
                "--output",
                str(output),
                "--baseline",
                str(baseline),
            )
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["baseline_diff"] is not None
    assert payload["units"][0]["status"] == "gap"
    assert payload["scope"]["include_covered"] is True


@pytest.mark.kiwi_id(2523)
def test_invalid_inputs_exit_two(tmp_path: Path) -> None:
    """日期 / 显式豁免缺失 / 基线缺失 / 基线加过滤 → 退出码 2。"""
    assert coverage_cli.main(_argv("--as-of", "2026-13-01")) == 2
    assert coverage_cli.main(_argv("--exemptions", str(tmp_path / "missing.json"))) == 2
    assert coverage_cli.main(_argv("--baseline", str(tmp_path / "missing.json"))) == 2
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    assert coverage_cli.main(_argv("--baseline", str(baseline), "--product-key", "platform")) == 2


@pytest.mark.kiwi_id(2523)
def test_strict_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量等价 --strict（参数优先）。"""
    monkeypatch.setenv("BMS_HELP_COVERAGE_STRICT", "1")
    assert coverage_cli.main(_argv("--as-of", "2026-11-17")) == 1


@pytest.mark.kiwi_id(2523)
def test_helper_paths_and_renderers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """豁免路径缺省取配置、显式优先；三种渲染器可用。"""
    explicit = coverage_cli._exemption_paths(_argv("explicit.json"))  # pyright: ignore[reportPrivateUsage]
    assert list(explicit) == ["explicit.json"]

    fake_settings = SimpleNamespace(
        help_coverage=SimpleNamespace(exemption_paths=["configured.json"]),
    )
    monkeypatch.setattr(coverage_cli, "get_settings", lambda: fake_settings)
    configured = coverage_cli._exemption_paths(_argv())  # pyright: ignore[reportPrivateUsage]
    assert list(configured) == ["configured.json"]

    ledger = build_help_coverage_ledger(_snapshot(), as_of=AS_OF)
    assert "帮助覆盖率台账" in coverage_cli._render(ledger, "text")  # pyright: ignore[reportPrivateUsage]
    assert "| 类别 |" in coverage_cli._render(ledger, "markdown")  # pyright: ignore[reportPrivateUsage]
    assert '"kind": "help-coverage"' in coverage_cli._render(ledger, "json")  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2523)
def test_exemption_set_type_is_frozen() -> None:
    """豁免集合为不可变值对象（防止运行期被改写）。"""
    empty = HelpCoverageExemptionSet(
        entries=ConcurrentStableFrozenList(),
        paths=ConcurrentStableFrozenList(),
    )
    assert isinstance(empty.entries, ConcurrentStableFrozenList)
    entry = HelpCoverageExemption(
        kind="action",
        key="user:create",
        owner="08_04",
        reason="测试用的豁免理由不少于十个字",
        expires_at=AS_OF,
    )
    assert entry.product_key is None
