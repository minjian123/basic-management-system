"""Schemathesis 契约冒烟命令行：源码起真实服务进程 + Schemathesis 容器打真实服务（零 Broker）。

用法::

    uv run python -m ops.contract_smoke run
    uv run python -m ops.contract_smoke run --service platform --max-examples 50

口径见任务 09_03 详细设计：
- 被测服务为**源码直跑的真实进程**（`uv run python -m bms_{service}`，`BMS_ENV=dev` / SQLite，
  `BMS_SERVER__PORT=<分配端口>`），不依赖子流水线推送的按提交镜像；
- Schemathesis 走固定 tag 镜像 `schemathesis/schemathesis:4.28.0`，以 `--network container:<job 容器>`
  与 job 容器共享网络命名空间，经 `127.0.0.1:<port>` 打真实服务；
- 只读方法（GET / HEAD）+ 有限样例 + 仅 `not_a_server_error`（无 5xx）；非 2xx（4xx）视为可达通过；
- 逐服务串行，任一失败即非零退出。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from bms_core.db.migration import BACKEND_ROOT
from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.service_contract import CONTRACTS_DIR, contract_file_name

SCHEMATHESIS_IMAGE = "schemathesis/schemathesis:4.28.0"
"""Schemathesis 固定 tag 镜像（预拉与镜像清单见《契约门禁与契约测试使用说明》）。"""

SCHEMATHESIS_COMMAND = "docker"
"""Schemathesis 调用命令（经 docker 运行固定 tag 镜像；单测可注入桩替换）。"""

DEFAULT_MAX_EXAMPLES = 50
"""每服务属性测试样例上限（冒烟口径，非全量）。"""

BASE_PORT = 18000
"""被测服务端口基址（逐服务 +索引，避免与宿主 8000 冲突）。"""

READ_METHODS = ("GET", "HEAD")
"""冒烟只读方法（不写数据、不依赖登录链路）。"""

HEALTH_PATH = "/healthz"
"""健康检查路径（就绪判定）。"""

Probe = Callable[[str], object]
"""健康探测函数类型（默认 urlopen；单测注入桩）。"""


@dataclass(frozen=True)
class SmokeResult:
    """单服务冒烟结果。"""

    service: str
    ok: bool
    detail: str = ""


def service_port(index: int) -> int:
    """服务监听端口。

    Args:
        index: 服务在目标集合中的序号（0 起）。

    Returns:
        int: `BASE_PORT + index`。
    """
    return BASE_PORT + index


def start_service_command(service_key: str) -> list[str]:
    """启动真实服务进程的命令（源码直跑）。

    Args:
        service_key: 服务标识。

    Returns:
        list[str]: `uv run python -m bms_<service>`。
    """
    return ["uv", "run", "python", "-m", f"bms_{service_key}"]


def service_env(base_env: Mapping[str, str], port: int) -> dict[str, str]:
    """构造服务进程环境变量（dev/SQLite + 指定端口）。

    Args:
        base_env: 基础环境变量（通常 `os.environ`）。
        port: 服务监听端口。

    Returns:
        dict[str, str]: 注入 `BMS_ENV` / `BMS_SERVER__PORT` 后的环境。
    """
    env = dict(base_env)
    env["BMS_ENV"] = "dev"
    env["BMS_SERVER__PORT"] = str(port)
    return env


def resolve_container_ref() -> str:
    """当前 job 容器引用（供 Schemathesis 容器 `--network container:` 共享网络命名空间）。

    Returns:
        str: 容器引用（Docker executor 下 `$HOSTNAME` 即容器标识）；空则提示人工指定。
    """
    return os.environ.get("HOSTNAME", "").strip()


def schemathesis_command(
    service_key: str,
    port: int,
    schema_dir: Path,
    *,
    container_ref: str,
    image: str = SCHEMATHESIS_IMAGE,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> list[str]:
    """构造 Schemathesis 打真实服务的命令行。

    Args:
        service_key: 服务标识。
        port: 被测服务端口。
        schema_dir: 契约快照目录（挂载为 `/schemas`）。
        container_ref: job 容器引用（`--network container:` 目标）。
        image: Schemathesis 镜像。
        max_examples: 每服务样例上限。

    Returns:
        list[str]: 完整命令行（docker run … schemathesis run …）。
    """
    command = [
        SCHEMATHESIS_COMMAND,
        "run",
        "--rm",
        "--network",
        f"container:{container_ref}",
        "-v",
        f"{schema_dir}:/schemas:ro",
        image,
        "run",
        f"/schemas/{contract_file_name(service_key)}",
        "--url",
        f"http://127.0.0.1:{port}",
        "--max-examples",
        str(max_examples),
        "--checks",
        "not_a_server_error",
        "--suppress-health-check",
        "all",
    ]
    for method in READ_METHODS:
        command += ["--include-method", method]
    return command


def _default_probe(url: str) -> object:
    """默认健康探测（urlopen，2xx 即就绪）。

    Args:
        url: 健康检查地址。

    Returns:
        object: urlopen 响应（非 None 即视为成功）。
    """
    return urllib.request.urlopen(url, timeout=2)


def wait_for_health(
    port: int,
    *,
    attempts: int = 30,
    interval: float = 1.0,
    probe: Probe = _default_probe,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """轮询服务 `/healthz` 直到就绪或超时。

    Args:
        port: 服务端口。
        attempts: 最大探测次数。
        interval: 探测间隔（秒）。
        probe: 健康探测函数（单测注入桩）。
        sleep: 休眠函数（单测注入桩）。

    Returns:
        bool: 就绪 True。
    """
    url = f"http://127.0.0.1:{port}{HEALTH_PATH}"
    for _ in range(attempts):
        try:
            probe(url)
            return True
        except urllib.error.URLError, OSError:
            sleep(interval)
    return False


def summarize(results: Sequence[SmokeResult]) -> int:
    """汇总冒烟结果。

    Args:
        results: 各服务结果。

    Returns:
        int: 退出码（0 全部通过；1 存在失败）。
    """
    failed = [result for result in results if not result.ok]
    for result in results:
        status = "通过" if result.ok else f"失败（{result.detail}）"
        print(f"[contract_smoke] 服务 {result.service}：{status}")
    if failed:
        print(f"[contract_smoke] 不通过：{len(failed)} / {len(results)} 个服务冒烟失败", file=sys.stderr)
        return 1
    print(f"[contract_smoke] 通过：{len(results)} 个服务 Schemathesis 冒烟通过")
    return 0


def run(
    root: Path,
    *,
    services: Sequence[str] | None = None,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
    image: str = SCHEMATHESIS_IMAGE,
    container_ref: str | None = None,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = subprocess.run,
    base_env: Mapping[str, str] | None = None,
) -> int:
    """逐服务起真实进程 → Schemathesis 打 → 停进程，汇总结果。

    Args:
        root: 仓库根。
        services: 目标服务（缺省取全部启用服务）。
        max_examples: 每服务样例上限。
        image: Schemathesis 镜像。
        container_ref: job 容器引用（缺省取 `$HOSTNAME`）。
        runner: 子进程执行器（单测注入桩）。
        base_env: 基础环境变量（缺省 `os.environ`）。

    Returns:
        int: 退出码（0 全部通过；1 存在失败 / 容器引用缺失）。
    """
    targets = list(services) if services is not None else list(enabled_service_keys())
    reference = container_ref if container_ref is not None else resolve_container_ref()
    if not reference:
        print("[contract_smoke] 无法解析 job 容器引用（$HOSTNAME 为空）：无法与 Schemathesis 共享网络", file=sys.stderr)
        return 1
    schema_dir = root / CONTRACTS_DIR
    env_base = base_env if base_env is not None else os.environ
    results: list[SmokeResult] = []
    for index, service_key in enumerate(targets):
        port = service_port(index)
        process = subprocess.Popen(
            start_service_command(service_key),
            cwd=BACKEND_ROOT,
            env=service_env(env_base, port),
        )
        try:
            if not wait_for_health(port):
                results.append(SmokeResult(service_key, False, "启动 / 就绪超时"))
                continue
            completed = runner(
                schemathesis_command(
                    service_key, port, schema_dir, container_ref=reference, image=image, max_examples=max_examples
                )
            )
            ok = completed.returncode == 0
            results.append(SmokeResult(service_key, ok, "" if ok else f"Schemathesis 返回码 {completed.returncode}"))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    return summarize(results)


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="Schemathesis 契约冒烟（源码起真实服务 + 容器打）")
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--root", type=Path, default=BACKEND_ROOT.parent, help="仓库根（缺省自动定位）")
    parser.add_argument("--service", help="单个服务标识（缺省全部启用服务）")
    parser.add_argument("--max-examples", type=int, default=DEFAULT_MAX_EXAMPLES, help="每服务样例上限")
    parser.add_argument("--image", default=SCHEMATHESIS_IMAGE, help="Schemathesis 镜像（缺省固定 tag）")
    parser.add_argument("--container-ref", default=None, help="job 容器引用（缺省取 $HOSTNAME）")
    args = parser.parse_args(argv)
    services = [args.service] if args.service else None
    return run(
        args.root,
        services=services,
        max_examples=args.max_examples,
        image=args.image,
        container_ref=cast("str | None", args.container_ref),
    )


if __name__ == "__main__":
    raise SystemExit(main())
