"""契约门禁命令行：独立基线管理 + oasdiff 破坏性变更比对 + 契约破坏数推送。

用法::

    uv run python -m ops.contract_gate check            # 基线 ↔ 实时公开契约，破坏性变更即失败
    uv run python -m ops.contract_gate check --metrics-out /tmp/m.txt   # 同时写出破坏数指标文本
    uv run python -m ops.contract_gate baseline-update --service platform
    uv run python -m ops.contract_gate baseline-update --all
    uv run python -m ops.contract_gate push-metrics --file /tmp/m.txt --gateway http://127.0.0.1:9092

口径见任务 09_03 详细设计：
- 基线 `deploy/contracts/baseline/<service>.json` 为**已放行的兼容契约**（入 Git，仅经评审更新）；
- 当前值为**实时公开契约**（`contract_snapshot.build_openapi` 内存构建后确定性渲染），不依赖已提交快照；
- 比对用 `tufin/oasdiff:v1.32.1` 的 `breaking`（「只加不删」），破坏性变更即非零退出并输出中文清单；
- 破坏数按 `bms_contract_breaking_total{service}`（08_02 口径）经 Pushgateway 推送，推送失败不阻断门禁结论。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.service_contract import (
    BASELINE_DIR,
    CONTRACTS_DIR,
    contract_file_name,
    render_contract_json,
)
from ops.contract_snapshot import build_openapi

OASDIFF_IMAGE = "tufin/oasdiff:v1.32.1"
"""oasdiff 固定 tag 镜像（预拉与镜像清单见《契约门禁与契约测试使用说明》）。"""

OASDIFF_COMMAND = "docker"
"""oasdiff 调用命令（经 docker 运行固定 tag 镜像；单测可注入桩替换）。"""

PUSHGATEWAY_JOB = "bms-ci"
"""Pushgateway 作业分组（与发布度量同组 `/metrics/job/bms-ci`）。"""

METRIC_NAME = "bms_contract_breaking_total"
"""契约破坏数指标名（08_02 已登记口径；gauge，标签 `service`）。"""

_ERROR_LEVELS = frozenset({"3", "err", "error"})
"""oasdiff 破坏性变更等级（数值 3 = ERR；文本 `err` / `error` 兼容）。"""

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]
"""子进程执行器类型（默认 docker；单测注入桩，不真联）。"""

DiffRunner = Callable[[Path, Path, str], tuple[int, str, str]]
"""单次 oasdiff 比对执行器类型：`(基线, 当前, 镜像) -> (返回码, stdout, stderr)`。"""


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """默认子进程执行器（docker）。

    Args:
        command: 完整命令行。

    Returns:
        subprocess.CompletedProcess[str]: 执行结果（不抛异常，由调用方判返回码）。
    """
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


@dataclass(frozen=True)
class BreakingResult:
    """单服务契约比对结果。"""

    service: str
    count: int
    raw: str
    ok: bool
    error: str = ""


def contracts_dir(root: Path) -> Path:
    """当前公开契约快照目录。

    Args:
        root: 仓库根。

    Returns:
        Path: `<root>/deploy/contracts`。
    """
    return root / CONTRACTS_DIR


def baseline_dir(root: Path) -> Path:
    """契约基线目录。

    Args:
        root: 仓库根。

    Returns:
        Path: `<root>/deploy/contracts/baseline`。
    """
    return root / BASELINE_DIR


def baseline_path(root: Path, service_key: str) -> Path:
    """单服务契约基线文件路径。

    Args:
        root: 仓库根。
        service_key: 服务标识。

    Returns:
        Path: `<root>/deploy/contracts/baseline/<service_key>.json`。
    """
    return baseline_dir(root) / contract_file_name(service_key)


def count_breaking(raw: str) -> int:
    """从 oasdiff 输出解析破坏性变更条目数。

    Args:
        raw: oasdiff `--format json` 的标准输出。

    Returns:
        int: 破坏性变更条目数（空输出 / 解析失败回退按非空行计）。
    """
    text = raw.strip()
    if not text:
        return 0
    try:
        decoded: object = json.loads(text)
    except json.JSONDecodeError:
        return sum(1 for line in text.splitlines() if line.strip())
    if isinstance(decoded, list):
        rows = cast("list[object]", decoded)
        items = [cast("dict[str, object]", row) for row in rows if isinstance(row, dict)]
        levels = [str(item.get("level", "")).lower() for item in items]
        if any(level in _ERROR_LEVELS for level in levels):
            return sum(1 for level in levels if level in _ERROR_LEVELS)
        return len(rows)
    if isinstance(decoded, dict):
        nested = cast("dict[str, object]", decoded).get("breaking")
        if isinstance(nested, list):
            return len(cast("list[object]", nested))
    return 1


def oasdiff_args() -> list[str]:
    """oasdiff `breaking` 子命令参数（容器内路径 `/base.json` / `/cur.json`）。

    Returns:
        list[str]: `["breaking", "--fail-on", "ERR", "--format", "json", "/base.json", "/cur.json"]`。
    """
    return ["breaking", "--fail-on", "ERR", "--format", "json", "/base.json", "/cur.json"]


def docker_diff(
    baseline: Path,
    current: Path,
    image: str,
    *,
    run: Runner = _run_command,
) -> tuple[int, str, str]:
    """用 oasdiff 容器比对两份契约，返回 `(返回码, stdout, stderr)`。

    **不使用 bind mount**：契约门禁 job 运行在容器内，其路径（`$CI_PROJECT_DIR` / `/tmp`）在
    宿主 daemon 上不可见，`docker run -v <job 路径>` 会挂到空目录（实测 oasdiff 报 102）。
    故改用 `docker create` + `docker cp`（文件经 daemon 流式复制）+ `docker start -a`（回传退出码）。

    Args:
        baseline: 基线契约文件（job 容器内路径）。
        current: 当前契约文件（job 容器内路径）。
        image: oasdiff 镜像（含 tag）。
        run: 子进程执行器（单测注入桩）。

    Returns:
        tuple[int, str, str]: oasdiff 返回码 / 标准输出 / 标准错误。
    """
    name = f"bms-contract-gate-{os.getpid()}-{baseline.stem}"
    run([OASDIFF_COMMAND, "rm", "-f", name])
    created = run([OASDIFF_COMMAND, "create", "--name", name, image, *oasdiff_args()])
    if created.returncode != 0:
        return created.returncode, created.stdout or "", created.stderr or ""
    try:
        for source, target in ((baseline, "/base.json"), (current, "/cur.json")):
            copied = run([OASDIFF_COMMAND, "cp", str(source), f"{name}:{target}"])
            if copied.returncode != 0:
                return copied.returncode, copied.stdout or "", copied.stderr or ""
        started = run([OASDIFF_COMMAND, "start", "-a", name])
        return started.returncode, started.stdout or "", started.stderr or ""
    finally:
        run([OASDIFF_COMMAND, "rm", "-f", name])


def compare_service(
    root: Path,
    service_key: str,
    *,
    image: str = OASDIFF_IMAGE,
    diff: DiffRunner = docker_diff,
) -> BreakingResult:
    """比对单服务基线 ↔ 实时公开契约。

    Args:
        root: 仓库根。
        service_key: 服务标识。
        image: oasdiff 镜像。
        diff: 比对执行器（缺省 `docker_diff`；单测注入桩）。

    Returns:
        BreakingResult: 比对结果（`ok=False` 表示工具 / 构建失败，非破坏性变更）。
    """
    baseline = baseline_path(root, service_key)
    if not baseline.is_file():
        return BreakingResult(service_key, 0, "", False, error=f"基线缺件：{baseline}")
    try:
        openapi = build_openapi(service_key)
    except RuntimeError as exc:
        return BreakingResult(service_key, 0, "", False, error=f"契约构建失败：{exc}")
    with tempfile.TemporaryDirectory(prefix="bms-contract-") as tmp:
        current = Path(tmp) / contract_file_name(service_key)
        current.write_text(render_contract_json(openapi), encoding="utf-8")
        try:
            returncode, stdout, stderr = diff(baseline, current, image)
        except OSError as exc:
            return BreakingResult(
                service_key,
                0,
                "",
                False,
                error=f"oasdiff 调用失败：{exc}（确认已预拉 {image}）",
            )
    raw = (stdout or "") + (stderr or "")
    if returncode not in (0, 1):
        return BreakingResult(
            service_key,
            0,
            raw.strip(),
            False,
            error=f"oasdiff 返回码 {returncode}（确认已预拉 {image}）：{raw.strip()}",
        )
    return BreakingResult(service_key, count_breaking(stdout or ""), raw.strip(), True)


def _metrics_line(service_key: str, count: int) -> str:
    """构造单服务破坏数指标行（Pushgateway 文本格式）。

    Args:
        service_key: 服务标识。
        count: 破坏性变更条目数。

    Returns:
        str: `bms_contract_breaking_total{service="x"} N`。
    """
    return f'{METRIC_NAME}{{service="{service_key}"}} {count}'


def check(
    root: Path,
    *,
    services: Sequence[str] | None = None,
    image: str = OASDIFF_IMAGE,
    diff: DiffRunner = docker_diff,
    metrics_out: Path | None = None,
) -> int:
    """逐服务比对基线 ↔ 实时公开契约，破坏性变更即失败。

    Args:
        root: 仓库根。
        services: 目标服务（缺省取全部启用服务）。
        image: oasdiff 镜像。
        diff: 比对执行器（缺省 `docker_diff`；单测注入桩）。
        metrics_out: 破坏数指标文本输出路径（存在即写出；供 after_script 推送）。

    Returns:
        int: 退出码（0 全部兼容；1 存在破坏性变更 / 缺件 / 工具失败）。
    """
    targets = list(services) if services is not None else list(enabled_service_keys())
    metrics: list[str] = []
    problems: list[BreakingResult] = []
    for service_key in targets:
        result = compare_service(root, service_key, image=image, diff=diff)
        if not result.ok:
            print(f"[contract_gate] 服务 {service_key}：{result.error}", file=sys.stderr)
            problems.append(result)
            continue
        metrics.append(_metrics_line(service_key, result.count))
        if result.count:
            problems.append(result)
            print(f"[contract_gate] 服务 {service_key}：检测到 {result.count} 项破坏性变更（基线 → 当前公开契约）")
            for line in result.raw.splitlines():
                if line.strip():
                    print(f"    {line}")
            print(
                f"    若为预期破坏性变更：uv run python -m ops.contract_gate baseline-update --service {service_key}"
                "（更新基线后提交并走评审合入；确需破坏时应升大版本 /api/v2 并行）"
            )
    if metrics_out is not None:
        metrics_out.write_text("".join(f"{line}\n" for line in metrics), encoding="utf-8")
    if problems:
        print(f"[contract_gate] 不通过：{len(problems)} 个服务存在破坏性变更或异常", file=sys.stderr)
        return 1
    print(f"[contract_gate] 通过：{len(targets)} 个服务公开契约与基线兼容")
    return 0


def baseline_update(root: Path, *, services: Sequence[str], current_dir: Path | None = None) -> int:
    """把当前快照复制为基线（预期破坏性变更时人工执行；不自动提交）。

    Args:
        root: 仓库根。
        services: 目标服务集合。
        current_dir: 当前快照目录（缺省 `<root>/deploy/contracts`）。

    Returns:
        int: 退出码（0 全部成功；1 有缺件）。
    """
    source_dir = current_dir if current_dir is not None else contracts_dir(root)
    target_dir = baseline_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for service_key in services:
        source = source_dir / contract_file_name(service_key)
        if not source.is_file():
            print(f"[contract_gate] 当前快照缺件：{source}", file=sys.stderr)
            failures += 1
            continue
        target = baseline_path(root, service_key)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[contract_gate] 已更新基线：{target}")
    return 1 if failures else 0


def push_metrics(metrics_file: Path, gateway: str) -> int:
    """把破坏数指标文本推送 Pushgateway（失败仅提示，不阻断）。

    Args:
        metrics_file: 指标文本文件（每行一个指标，末尾换行）。
        gateway: Pushgateway 基址（如 `http://127.0.0.1:9092`）。

    Returns:
        int: 始终 0（推送为次要信号）。
    """
    if not gateway:
        print("[contract_gate] 未配置 Pushgateway 地址：跳过破坏数推送")
        return 0
    if not metrics_file.is_file():
        print(f"[contract_gate] 指标文件不存在（{metrics_file}）：跳过破坏数推送")
        return 0
    payload = metrics_file.read_text(encoding="utf-8")
    if not payload.endswith("\n"):
        payload += "\n"
    url = gateway.rstrip("/") + f"/metrics/job/{PUSHGATEWAY_JOB}"
    request = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"[contract_gate] 破坏数已推送 {url}（HTTP {response.status}）")
    except urllib.error.URLError as exc:
        print(f"[contract_gate] 破坏数推送失败（不阻断门禁）：{exc}")
    except OSError as exc:
        print(f"[contract_gate] 破坏数推送失败（不阻断门禁）：{exc}")
    return 0


def _select_services(service: str | None, all_services: bool) -> list[str]:
    """解析目标服务集合。

    Args:
        service: 单个服务标识（可空）。
        all_services: 是否全部启用服务。

    Returns:
        list[str]: 目标服务列表（缺省全部启用服务）。

    Raises:
        SystemExit: 既未指定服务也未指定 `--all` 时。
    """
    if all_services:
        return list(enabled_service_keys())
    if service:
        return [service]
    raise SystemExit("请指定 --service <服务> 或 --all")


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="契约门禁：基线管理 / oasdiff 破坏性比对 / 破坏数推送")
    parser.add_argument("command", choices=("check", "baseline-update", "push-metrics"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="仓库根（缺省自动定位）")
    parser.add_argument("--service", help="单个服务标识（check / baseline-update）")
    parser.add_argument("--all", dest="all_services", action="store_true", help="全部启用服务（baseline-update）")
    parser.add_argument("--image", default=OASDIFF_IMAGE, help="oasdiff 镜像（缺省固定 tag）")
    parser.add_argument("--metrics-out", type=Path, help="破坏数指标文本输出路径（check）")
    parser.add_argument("--file", dest="metrics_file", type=Path, help="指标文本文件（push-metrics）")
    parser.add_argument("--gateway", default="", help="Pushgateway 基址（push-metrics）")
    args = parser.parse_args(argv)
    if args.command == "check":
        services = [args.service] if args.service else None
        return check(args.root, services=services, image=args.image, metrics_out=args.metrics_out)
    if args.command == "baseline-update":
        return baseline_update(args.root, services=_select_services(args.service, args.all_services))
    if args.metrics_file is None:
        raise SystemExit("push-metrics 需 --file <指标文本>")
    return push_metrics(args.metrics_file, args.gateway)


if __name__ == "__main__":
    raise SystemExit(main())
