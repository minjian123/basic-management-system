"""种子编排 CLI 用例（07B `02_03`；详设 §5 用例 19~24 / 27 的 CLI 侧）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：参数契约、退出码 64（`EX_USAGE`）、HTTP 400 映射 64、报告渲染（成功 / 冲突 /
执行失败 / 前置错误）、`--json` 输出、网络失败退 2。
"""

import json
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.tenant.seed import cli
from bms_core.tenant.seed.orchestrator import EXIT_USAGE

# ---- 参数契约（用例 22）----


def test_parser_accepts_documented_flags() -> None:
    """详设 §3.12 的 8 个参数均可解析。"""
    args = cli.build_parser().parse_args(
        [
            "--tenant",
            "demo",
            "--only",
            "a",
            "--only",
            "b",
            "--skip",
            "c",
            "--require",
            "d",
            "--dry-run",
            "--json",
            "--timeout",
            "42",
            "--base-url",
            "http://x",
        ]
    )
    assert args.tenant == "demo"
    assert args.only == ["a", "b"]
    assert args.skip == ["c"]
    assert args.require == ["d"]
    assert args.dry_run is True
    assert args.json is True
    assert args.timeout == 42.0
    assert args.base_url == "http://x"


def test_parser_defaults() -> None:
    """缺省值：租户空串、不筛选、非 dry-run、超时 300s、基址空（走环境变量 / 回环）。"""
    args = cli.build_parser().parse_args([])
    assert args.tenant == ""
    assert (args.only, args.skip, args.require) == ([], [], [])
    assert args.dry_run is False
    assert args.json is False
    assert args.timeout == 300.0
    assert args.base_url == ""


def test_unknown_flag_exits_64() -> None:
    """用例 22：参数错误退 **64**（不是 argparse 缺省的 2，避免与「执行失败」混淆）。"""
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--no-such-flag"])
    assert exc.value.code == EXIT_USAGE


def test_missing_value_exits_64() -> None:
    """用例 22 补充：选项缺取值同样退 64。"""
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--tenant"])
    assert exc.value.code == EXIT_USAGE


# ---- 报告渲染（用例 23 / 24）----


def test_render_report_success() -> None:
    """用例 23：成功报告渲染表头 + 逐项行 + 汇总行。"""
    text = cli.render_report(
        {
            "exitCode": 0,
            "reports": [
                {"name": "seed-module", "source": "platform", "status": "ok", "note": ""},
                {"name": "mdm-admin-codes", "source": "mdm", "status": "ok", "note": ""},
            ],
        }
    )
    assert "种子" in text and "来源" in text and "状态" in text
    assert "seed-module" in text and "mdm-admin-codes" in text
    assert "全部成功" in text


def test_render_report_conflicts() -> None:
    """用例 5/24：冲突报告渲染「数据冲突」段与提示行。"""
    text = cli.render_report(
        {
            "exitCode": 1,
            "reports": [],
            "conflicts": ["种子 seed-menu：sys_business 与声明不一致"],
        }
    )
    assert "[数据冲突]" in text
    assert "sys_business 与声明不一致" in text
    assert "未进入事务" in text


def test_render_report_execute_failure() -> None:
    """用例 15/24：执行失败渲染「已回滚，无脏数据」提示。"""
    text = cli.render_report(
        {
            "exitCode": 2,
            "reports": [{"name": "a", "source": "platform", "status": "rolled_back", "note": "← 失败：x"}],
        }
    )
    assert "已回滚" in text
    assert "无脏数据" in text


def test_render_report_precheck_error() -> None:
    """用例 4/24：前置错误渲染错误段与提示行。"""
    text = cli.render_report({"exitCode": 3, "errors": ["种子重名：seed-x"]})
    assert "[前置错误]" in text
    assert "编排前置错误" in text


def test_render_report_unknown_exit_code_falls_back() -> None:
    """未知退出码走兜底文案（不抛错）。"""
    text = cli.render_report({"exitCode": 99})
    assert "编排前置错误" in text


def test_render_report_tolerates_non_dict() -> None:
    """非 dict 入参按空对象处理（防御性，不抛错）。"""
    assert "全部成功" in cli.render_report(cast_any("not a dict"))


def cast_any(value: Any) -> Any:
    """把任意值原样返回（规避静态类型告警）。

    Args:
        value: 任意值。

    Returns:
        Any: 原值。
    """
    return value


# ---- main()：调用 / 退出码 / 输出 ----


class _Recorder:
    """`_call` 替身记录器：可返回预设数据或抛指定异常。"""

    def __init__(self, *, data: Any = None, error: Exception | None = None) -> None:
        """初始化。

        Args:
            data: 预设返回数据。
            error: 预设异常。
        """
        self.data = data if data is not None else {}  # pyright: ignore
        self.error = error
        self.bodies: ConcurrentStableList[Any] = ConcurrentStableList()
        self.urls: ConcurrentStableList[str] = ConcurrentStableList()

    def __call__(self, base_url: str, body: Any) -> Any:
        """记录调用并返回 / 抛出。

        Args:
            base_url: 服务基址。
            body: 请求体。

        Returns:
            Any: 预设数据。

        Raises:
            Exception: 预设异常。
        """
        self.urls.add(base_url)
        self.bodies.add(body)
        if self.error is not None:
            raise self.error
        return self.data  # pyright: ignore


def _patch_call(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    """把 `cli._call` 替换为替身。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        recorder: 替身。
    """
    monkeypatch.setattr(cli, "_call", recorder)


def test_main_returns_exit_code_from_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """用例 14/23：`main` 返回服务给出的退出码并打印渲染报告。"""
    recorder = _Recorder(data={"exitCode": 0, "reports": [{"name": "a", "status": "ok"}]})
    _patch_call(monkeypatch, recorder)
    assert cli.main(ConcurrentStableList(["--tenant", "demo"])) == 0
    out = capsys.readouterr().out
    assert "全部成功" in out


def test_main_passes_body_to_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求体字段与参数一一对应（租户 / 筛选 / dry-run / 超时）。"""
    recorder = _Recorder(data={"exitCode": 0})
    _patch_call(monkeypatch, recorder)
    cli.main(
        ConcurrentStableList(
            [
                "--tenant",
                "demo",
                "--only",
                "a",
                "--skip",
                "b",
                "--require",
                "c",
                "--dry-run",
                "--timeout",
                "9",
            ]
        )
    )
    body = recorder.bodies[0]
    assert body["tenant"] == "demo"
    assert body["only"] == ["a"]
    assert body["skip"] == ["b"]
    assert body["require"] == ["c"]
    assert body["dry_run"] is True
    assert body["timeout_seconds"] == 9.0


def test_main_json_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """用例 24：`--json` 输出机器可读 JSON（结构可解析、字段齐全）。"""
    payload = {"exitCode": 0, "reports": [{"name": "a", "status": "ok"}], "errors": [], "conflicts": []}
    _patch_call(monkeypatch, _Recorder(data=payload))
    assert cli.main(ConcurrentStableList(["--json"])) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["exitCode"] == 0
    assert set(parsed) == {"exitCode", "reports", "errors", "conflicts"}


def test_main_http_400_maps_to_64(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """用例 22：端点拒绝参数（HTTP 400）→ 退 **64**（参数错误，非执行失败）。"""
    _patch_call(monkeypatch, _Recorder(error=RuntimeError("编排端点返回 HTTP 400：参数非法")))
    assert cli.main(ConcurrentStableList(["--only", "ghost"])) == EXIT_USAGE
    assert "HTTP 400" in capsys.readouterr().out


def test_main_network_failure_returns_2(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """网络失败（非参数错）→ 退 2（执行失败口径）。"""
    _patch_call(monkeypatch, _Recorder(error=RuntimeError("无法连接编排端点")))
    assert cli.main(ConcurrentStableList([])) == 2
    assert "无法连接编排端点" in capsys.readouterr().out


# ---- 基址解析 ----


def test_base_url_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """基址解析：参数 > 环境变量 > 回环。"""
    monkeypatch.delenv("BMS_SEED_ORCHESTRATE_URL", raising=False)
    assert cli._base_url("http://arg/") == "http://arg"  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv("BMS_SEED_ORCHESTRATE_URL", "http://env/")
    assert cli._base_url("") == "http://env"  # pyright: ignore[reportPrivateUsage]
    assert cli._base_url("http://arg") == "http://arg"  # pyright: ignore[reportPrivateUsage]
    monkeypatch.delenv("BMS_SEED_ORCHESTRATE_URL")
    assert cli._base_url("") == cli.DEFAULT_BASE_URL  # pyright: ignore[reportPrivateUsage]


# ---- 用例 27：单步命令兼容 ----


def test_single_step_commands_still_available() -> None:
    """用例 27：既有单步命令（`ops.seed_menu` 等）保留 `main`，行为不变。"""
    from ops import seed_config, seed_menu, seed_module, seed_tables, seed_tenant

    for module in (seed_menu, seed_module, seed_tables, seed_tenant, seed_config):
        assert callable(module.main)


# ---- `_call` 网络路径（替身 urlopen；不起真实端口，避免 xdist 下端口 / 时序不稳）----


class _FakeResponse:
    """`urlopen` 返回替身（上下文管理器 + `read`）。"""

    def __init__(self, payload: bytes) -> None:
        """初始化。

        Args:
            payload: 响应体。
        """
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        """进入上下文。

        Returns:
            _FakeResponse: 自身。
        """
        return self

    def __exit__(self, *_args: object) -> None:
        """退出上下文（无资源需释放）。"""

    def read(self) -> bytes:
        """读响应体。

        Returns:
            bytes: 响应体。
        """
        return self._payload


def test_call_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call` 成功路径：解析 `data` 返回。"""
    import urllib.request

    payload = json.dumps({"code": 0, "data": {"exitCode": 0, "reports": []}}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(payload))  # pyright: ignore
    data: Any = cli._call("http://x", ConcurrentStableDict({"timeout_seconds": 1.0}))  # pyright: ignore[reportPrivateUsage]
    assert data["exitCode"] == 0


def test_call_http_error_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call`：非 2xx → `RuntimeError`（含状态码）。"""
    import io
    import urllib.error
    import urllib.request

    def _raise(*_a: Any, **_k: Any) -> Any:
        """抛 HTTPError。

        Args:
            *_a: 位置参数。
            **_k: 关键字参数。

        Raises:
            urllib.error.HTTPError: 恒定抛出。
        """
        raise urllib.error.HTTPError("http://x", 400, "Bad Request", {}, io.BytesIO(b'{"code": 10001}'))  # pyright: ignore

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(RuntimeError, match="HTTP 400"):
        cli._call("http://x", ConcurrentStableDict({"timeout_seconds": 1.0}))  # pyright: ignore[reportPrivateUsage]


def test_call_invalid_json_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call`：响应非 JSON → `RuntimeError`。"""
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(b"<html>"))  # type: ignore[reportUnknownLambdaType]
    with pytest.raises(RuntimeError, match="非 JSON"):
        cli._call("http://x", ConcurrentStableDict({"timeout_seconds": 1.0}))  # pyright: ignore[reportPrivateUsage]


def test_call_non_object_json_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call`：响应是 JSON 但不是对象 → `RuntimeError`。"""
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(b"[1, 2]"))  # type: ignore[reportUnknownLambdaType]
    with pytest.raises(RuntimeError, match="非 JSON 对象"):
        cli._call("http://x", ConcurrentStableDict({"timeout_seconds": 1.0}))  # pyright: ignore[reportPrivateUsage]


def test_call_connection_failure_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call`：连接失败 → `RuntimeError`（无法连接）。"""
    import urllib.error
    import urllib.request

    def _raise(*_a: Any, **_k: Any) -> Any:
        """抛 URLError。

        Args:
            *_a: 位置参数。
            **_k: 关键字参数。

        Raises:
            urllib.error.URLError: 恒定抛出。
        """
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(RuntimeError, match="无法连接编排端点"):
        cli._call("http://x", ConcurrentStableDict({"timeout_seconds": 1.0}))  # pyright: ignore[reportPrivateUsage]


def test_call_missing_data_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_call`：响应无 `data` → 返回空映射（不抛错）。"""
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(b'{"code": 0}'))  # type: ignore[reportUnknownLambdaType]
    data: Any = cli._call("http://x", ConcurrentStableDict({"timeout_seconds": 1.0}))  # pyright: ignore[reportPrivateUsage]
    assert list(data) == []


def test_main_uses_env_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main` 走 `--base-url` 缺省时读环境变量。"""
    recorded: ConcurrentStableList[str] = ConcurrentStableList()

    def _fake_call(base_url: str, body: Any) -> Any:
        """记录基址并返回空结果。

        Args:
            base_url: 服务基址。
            body: 请求体。

        Returns:
            Any: 空结果。
        """
        del body
        recorded.add(base_url)
        return {"exitCode": 0}

    monkeypatch.setenv("BMS_SEED_ORCHESTRATE_URL", "http://env-host/")
    monkeypatch.setattr(cli, "_call", _fake_call)
    assert cli.main(ConcurrentStableList([])) == 0
    assert list(recorded) == ["http://env-host"]
