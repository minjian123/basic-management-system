"""Schemathesis 契约冒烟命令行：用**已构建服务镜像**起真实容器 + 容器打真实服务（零 Broker）。

用法::

    uv run python -m ops.contract_smoke run --service platform --image <registry>/bms-platform:$CI_COMMIT_SHORT_SHA

口径见任务 09_03 详细设计：
- 被测服务为**已构建的服务镜像**（子流水线 `service-build` 产物 `bms-{service}:$CI_COMMIT_SHORT_SHA`，
  固定 tag ⇒ 可固定重现），以 `docker run -d -e BMS_ENV=dev` 起容器，按其镜像 `HEALTHCHECK`
  （`/healthz`）就绪后开打；**不由本 CLI 源码起进程 / 不重复构建**；
- 每次只针对**本次变更的服务**（父流水线按服务 `rules:changes` 调度，未变更服务不跑）；
- Schemathesis 走固定 tag 镜像 `schemathesis/schemathesis:4.28.0`，以 `--network container:<服务容器>`
  与服务容器共享网络命名空间，经 `127.0.0.1:8000` 打真实服务；
- 只读方法（GET / HEAD）+ 每操作 1 例（冒烟）+ 仅 `not_a_server_error`（无 5xx）；
  排除基础设施端点（`/healthz` `/readyz` `/metrics`）；非 2xx（4xx）视为可达通过。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from bms_core.db.migration import BACKEND_ROOT
from bms_core.services.service_contract import CONTRACTS_DIR, contract_file_name

SCHEMATHESIS_IMAGE = "schemathesis/schemathesis:4.28.0"
"""Schemathesis 固定 tag 镜像（预拉与镜像清单见《契约门禁与契约测试使用说明》）。"""

CONTAINER_COMMAND = "docker"
"""容器命令（起服务容器 / 跑 Schemathesis；单测可注入桩替换）。"""

DEFAULT_MAX_EXAMPLES = 1
"""每操作样例上限（冒烟口径：1 例即证明服务可达且无 5xx，不做 fuzz）。"""

READ_METHODS = ("GET", "HEAD")
"""冒烟只读方法（不写数据、不依赖登录链路）。"""

EXCLUDED_PATHS = ("/healthz", "/readyz", "/metrics")
"""排除的基础设施端点（探针 / 指标；非业务契约，且无依赖时 503 属预期，不计入冒烟失败）。"""

SERVICE_PORT = 8000
"""服务容器监听端口（镜像内 `BMS_SERVER__PORT` 缺省 8000）。"""

HEALTH_ATTEMPTS = 60
"""服务容器就绪轮询次数（1s 一次，镜像 HEALTHCHECK `/healthz`）。"""

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]
"""子进程执行器类型（默认 docker；单测注入桩，不真联）。"""


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """默认子进程执行器（docker）。

    Args:
        command: 完整命令行。

    Returns:
        subprocess.CompletedProcess[str]: 执行结果（不抛异常，由调用方判返回码）。
    """
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


def service_container_name(service_key: str) -> str:
    """服务容器名（固定命名，便于 `--network container:` 引用与清理）。

    Args:
        service_key: 服务标识。

    Returns:
        str: `bms-smoke-<service>`。
    """
    return f"bms-smoke-{service_key}"


def schemathesis_args(service_key: str, *, max_examples: int = DEFAULT_MAX_EXAMPLES) -> list[str]:
    """Schemathesis 子命令参数（容器内 schema 路径 `/tmp/<服务>.json`）。

    Args:
        service_key: 服务标识。
        max_examples: 每操作样例上限。

    Returns:
        list[str]: `run … --url http://127.0.0.1:<port> …`。
    """
    command = [
        "run",
        f"/tmp/{contract_file_name(service_key)}",
        "--url",
        f"http://127.0.0.1:{SERVICE_PORT}",
        "--max-examples",
        str(max_examples),
        "--checks",
        "not_a_server_error",
        "--suppress-health-check",
        "all",
    ]
    for method in READ_METHODS:
        command += ["--include-method", method]
    for path in EXCLUDED_PATHS:
        command += ["--exclude-path", path]
    return command


def service_up(
    service_key: str,
    image: str,
    *,
    run: Runner = _run_command,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = HEALTH_ATTEMPTS,
) -> bool:
    """以已构建镜像起服务容器并等待其 `healthy`。

    Args:
        service_key: 服务标识。
        image: 服务镜像（含固定 tag）。
        run: 子进程执行器（单测注入桩）。
        sleep: 休眠函数（单测注入桩）。
        attempts: 就绪轮询次数。

    Returns:
        bool: 就绪 True（起容器失败或超时 False）。
    """
    name = service_container_name(service_key)
    run([CONTAINER_COMMAND, "rm", "-f", name])
    started = run([CONTAINER_COMMAND, "run", "-d", "--name", name, "-e", "BMS_ENV=dev", image])
    if started.returncode != 0:
        return False
    for _ in range(attempts):
        status = run([CONTAINER_COMMAND, "inspect", "-f", "{{.State.Health.Status}}", name])
        if (status.stdout or "").strip() == "healthy":
            return True
        sleep(1)
    return False


def service_down(service_key: str, *, run: Runner = _run_command) -> None:
    """停止并移除服务容器（幂等）。

    Args:
        service_key: 服务标识。
        run: 子进程执行器（单测注入桩）。
    """
    run([CONTAINER_COMMAND, "rm", "-f", service_container_name(service_key)])


def docker_schemathesis(
    service_key: str,
    schema_path: Path,
    *,
    service_container: str,
    image: str = SCHEMATHESIS_IMAGE,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
    run: Runner = _run_command,
) -> tuple[int, str, str]:
    """用 Schemathesis 容器打服务容器，返回 `(返回码, stdout, stderr)`。

    服务容器已就绪时，Schemathesis 容器以 `--network container:<服务容器>` 共享其网络命名空间，
    经 `127.0.0.1:<port>` 打真实服务；schema 经 `docker cp` 复制进容器 `/tmp`（**不用 `-v` 挂 job 路径**：
    门禁 job 在容器内，其路径在宿主 daemon 不可见，会挂到空目录）。

    Args:
        service_key: 服务标识。
        schema_path: schema 文件（job 容器内路径）。
        service_container: 服务容器名（`--network container:` 目标）。
        image: Schemathesis 镜像（含 tag）。
        max_examples: 每操作样例上限。
        run: 子进程执行器（单测注入桩）。

    Returns:
        tuple[int, str, str]: Schemathesis 返回码 / 标准输出 / 标准错误。
    """
    name = f"bms-contract-smoke-{os.getpid()}-{service_key}"
    run([CONTAINER_COMMAND, "rm", "-f", name])
    created = run(
        [
            CONTAINER_COMMAND,
            "create",
            "--name",
            name,
            "--network",
            f"container:{service_container}",
            image,
            *schemathesis_args(service_key, max_examples=max_examples),
        ]
    )
    if created.returncode != 0:
        return created.returncode, created.stdout or "", created.stderr or ""
    try:
        copied = run([CONTAINER_COMMAND, "cp", str(schema_path), f"{name}:/tmp/{contract_file_name(service_key)}"])
        if copied.returncode != 0:
            return copied.returncode, copied.stdout or "", copied.stderr or ""
        started = run([CONTAINER_COMMAND, "start", "-a", name])
        return started.returncode, started.stdout or "", started.stderr or ""
    finally:
        run([CONTAINER_COMMAND, "rm", "-f", name])


def _tail(text: str, limit: int = 30) -> str:
    """截取输出尾部（非空行），供失败时打印便于定位。

    Args:
        text: 原始输出。
        limit: 保留行数上限。

    Returns:
        str: 尾部文本。
    """
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])


def run(
    root: Path,
    *,
    service: str,
    image: str,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
    smoke_image: str = SCHEMATHESIS_IMAGE,
    run_cmd: Runner = _run_command,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """对单个服务：起已构建镜像容器 → 就绪 → Schemathesis 打 → 停容器。

    Args:
        root: 仓库根。
        service: 服务标识。
        image: 服务镜像（含固定 tag）。
        max_examples: 每操作样例上限。
        smoke_image: Schemathesis 镜像。
        run_cmd: 子进程执行器（单测注入桩）。
        sleep: 休眠函数（单测注入桩）。

    Returns:
        int: 退出码（0 通过；1 起容器 / 就绪失败或冒烟失败）。
    """
    schema_path = root / CONTRACTS_DIR / contract_file_name(service)
    if not service_up(service, image, run=run_cmd, sleep=sleep):
        print(f"[contract_smoke] 服务 {service}：容器启动 / 就绪失败（镜像 {image}）", file=sys.stderr)
        service_down(service, run=run_cmd)
        return 1
    try:
        returncode, stdout, stderr = docker_schemathesis(
            service,
            schema_path,
            service_container=service_container_name(service),
            image=smoke_image,
            max_examples=max_examples,
            run=run_cmd,
        )
    finally:
        service_down(service, run=run_cmd)
    if returncode == 0:
        print(f"[contract_smoke] 服务 {service}：Schemathesis 冒烟通过")
        return 0
    print(f"[contract_smoke] 服务 {service}：Schemathesis 返回码 {returncode}")
    print(_tail((stdout or "") + (stderr or "")))
    return 1


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="Schemathesis 契约冒烟（已构建镜像起容器 + 容器打）")
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--root", type=Path, default=BACKEND_ROOT.parent, help="仓库根（缺省自动定位）")
    parser.add_argument("--service", required=True, help="单个服务标识")
    parser.add_argument("--image", required=True, help="服务镜像（含固定 tag）")
    parser.add_argument("--max-examples", type=int, default=DEFAULT_MAX_EXAMPLES, help="每操作样例上限")
    parser.add_argument("--smoke-image", default=SCHEMATHESIS_IMAGE, help="Schemathesis 镜像（缺省固定 tag）")
    args = parser.parse_args(argv)
    return run(
        args.root,
        service=args.service,
        image=args.image,
        max_examples=args.max_examples,
        smoke_image=args.smoke_image,
    )


if __name__ == "__main__":
    raise SystemExit(main())
