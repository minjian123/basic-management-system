"""网关声明式配置命令行：由服务目录生成 / 校验 `deploy/gateway/apisix.yaml`。

用法::

    uv run python -m ops.gateway_config render          # 生成（覆盖写入配置）
    uv run python -m ops.gateway_config render --print  # 生成并打印
    uv run python -m ops.gateway_config check           # 零漂移校验（CI / 预检用）
    uv run python -m ops.gateway_config check --root .  # 指定仓库根

`check` 同时校验**请求体上限三方一致**（04-1-2）：边缘 nginx 模板（变量化声明）↔ 网关编排缺省值
↔ APISIX 启动配置，且该值 ≥ 文件上传整包上限（`file.upload.max_size` = 20MB，超限走分片）。

薄入口：真正的生成逻辑在 `bms_core/services/gateway_catalog.py`（可单测）。
为在无后端依赖的精简环境（CI `base-integrity` 的 python:3.14-slim）下也可运行，
本脚本仅依赖标准库 + `bms_core` 的 stdlib 导入链，并自行把共享库源码根加入 `sys.path`。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _BACKEND_ROOT / "libs" / "bms_core" / "src"
sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402
from bms_core.services.gateway_catalog import (  # noqa: E402
    render_apisix_config,
    render_apisix_yaml,
    validate_service_discovery,
)

REPO_ROOT = _BACKEND_ROOT.parent
"""仓库根（`backend/` 的父目录）。"""

CONFIG_RELATIVE = Path("deploy/gateway/apisix.yaml")
"""生成件相对仓库根的路径。"""

NGINX_TEMPLATE_RELATIVE = Path("deploy/gateway/nginx.conf.template")
"""边缘 nginx 模板（请求体上限声明落点，04-1-2）。"""

APISIX_CONFIG_RELATIVE = Path("deploy/gateway/config.yaml")
"""APISIX 启动配置（请求体上限纵深防御落点，04-1-2）。"""

COMPOSE_GATEWAY_RELATIVE = Path("deploy/compose/gateway.yml")
"""网关编排（请求体上限环境变量缺省落点，04-1-2）。"""

ENV_EXAMPLE_RELATIVE = Path("deploy/.env.example")
"""环境变量模板（请求体上限键位登记落点，04-1-2）。"""

BODY_SIZE_VARIABLE = "GATEWAY_MAX_BODY_SIZE"
"""请求体上限环境变量名（缺省 32m）。"""

UPLOAD_MAX_SIZE_BYTES = 20 * 1024 * 1024
"""文件上传整包上限（`file.upload.max_size` = 20MB = 20971520）；网关请求体上限须 ≥ 此值。"""

_NGINX_VARIABLE_PATTERN = re.compile(r"client_max_body_size\s+\$\{GATEWAY_MAX_BODY_SIZE\}\s*;")
_NGINX_ANY_PATTERN = re.compile(r"client_max_body_size\s+([^;]+);")
_COMPOSE_DEFAULT_PATTERN = re.compile(r"GATEWAY_MAX_BODY_SIZE:\s*\$\{GATEWAY_MAX_BODY_SIZE:-([^}]+)\}")
_ENV_EXAMPLE_PATTERN = re.compile(r"^GATEWAY_MAX_BODY_SIZE=(.*)$", re.MULTILINE)
_APISIX_BODY_SIZE_PATTERN = re.compile(r"client_max_body_size:\s*[\"']?([0-9]+\s*[kKmMgG]?)[\"']?")
_SIZE_UNITS = {"": 1, "k": 1024, "m": 1024 * 1024, "g": 1024 * 1024 * 1024}


def parse_size(text: str) -> int | None:
    """解析 nginx 风格体积字面量（`32m` / `1024k` / 纯字节数）。

    Args:
        text: 体积字面量。

    Returns:
        int | None: 字节数；不可解析为 None。
    """
    match = re.fullmatch(r"\s*(\d+)\s*([kKmMgG]?)\s*", text or "")
    if match is None:
        return None
    return int(match.group(1)) * _SIZE_UNITS[match.group(2).lower()]


def validate_body_size(root: Path) -> ConcurrentStableList[str]:
    """校验请求体上限三方一致且与文件上传口径对齐（04-1-2）。

    Args:
        root: 仓库根。

    Returns:
        ConcurrentStableList[str]: 违规说明（空列表即通过）。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    default_text: str | None = None
    default_bytes: int | None = None

    template = root / NGINX_TEMPLATE_RELATIVE
    if not template.is_file():
        problems.add(f"缺少边缘 nginx 模板：{NGINX_TEMPLATE_RELATIVE}")
    else:
        text = template.read_text(encoding="utf-8")
        if _NGINX_VARIABLE_PATTERN.search(text) is None:
            problems.add(
                f"边缘 nginx 模板须以 ${{{BODY_SIZE_VARIABLE}}} 变量化声明请求体上限：{NGINX_TEMPLATE_RELATIVE}"
            )
        literal = _NGINX_ANY_PATTERN.search(text)
        if literal is not None and _NGINX_VARIABLE_PATTERN.search(text) is None:
            problems.add(
                f"边缘 nginx 模板请求体上限不得硬编码（须经 ${{{BODY_SIZE_VARIABLE}}} 注入）：{NGINX_TEMPLATE_RELATIVE}"
            )

    compose = root / COMPOSE_GATEWAY_RELATIVE
    if not compose.is_file():
        problems.add(f"缺少网关编排：{COMPOSE_GATEWAY_RELATIVE}")
    else:
        match = _COMPOSE_DEFAULT_PATTERN.search(compose.read_text(encoding="utf-8"))
        if match is None:
            problems.add(
                f"网关编排须为 {BODY_SIZE_VARIABLE} 提供缺省值"
                f"（形如 ${{{BODY_SIZE_VARIABLE}:-32m}}）：{COMPOSE_GATEWAY_RELATIVE}"
            )
        else:
            default_text = match.group(1).strip()
            default_bytes = parse_size(default_text)
            if default_bytes is None:
                problems.add(f"网关编排 {BODY_SIZE_VARIABLE} 缺省值不可解析：{default_text!r}")

    apisix = root / APISIX_CONFIG_RELATIVE
    if not apisix.is_file():
        problems.add(f"缺少 APISIX 启动配置：{APISIX_CONFIG_RELATIVE}")
    else:
        match = _APISIX_BODY_SIZE_PATTERN.search(apisix.read_text(encoding="utf-8"))
        if match is None:
            problems.add(f"APISIX 启动配置缺请求体上限（client_max_body_size）：{APISIX_CONFIG_RELATIVE}")
        else:
            apisix_bytes = parse_size(match.group(1))
            if apisix_bytes is None:
                problems.add(f"APISIX 请求体上限不可解析：{match.group(1)!r}")
            elif default_bytes is not None and apisix_bytes != default_bytes:
                problems.add(
                    f"APISIX 请求体上限（{match.group(1)}）与边缘缺省值（{default_text}）不一致："
                    f"{APISIX_CONFIG_RELATIVE}"
                )

    env_example = root / ENV_EXAMPLE_RELATIVE
    if not env_example.is_file():
        problems.add(f"缺少环境变量模板：{ENV_EXAMPLE_RELATIVE}")
    else:
        match = _ENV_EXAMPLE_PATTERN.search(env_example.read_text(encoding="utf-8"))
        if match is None:
            problems.add(f"环境变量模板缺 {BODY_SIZE_VARIABLE} 键位：{ENV_EXAMPLE_RELATIVE}")
        elif default_bytes is not None and parse_size(match.group(1).strip()) != default_bytes:
            problems.add(
                f"环境变量模板 {BODY_SIZE_VARIABLE}（{match.group(1).strip()}）与编排缺省值（{default_text}）不一致："
                f"{ENV_EXAMPLE_RELATIVE}"
            )

    if default_bytes is not None and default_bytes < UPLOAD_MAX_SIZE_BYTES:
        problems.add(
            f"网关请求体上限（{default_text}）小于文件上传整包上限 20MB（{UPLOAD_MAX_SIZE_BYTES} 字节）："
            "整包直传将被网关先拒，须上调或改走更小整包上限"
        )
    return problems


def config_path(root: Path) -> Path:
    """生成件的绝对路径。

    Args:
        root: 仓库根。

    Returns:
        Path: `deploy/gateway/apisix.yaml` 路径。
    """
    return root / CONFIG_RELATIVE


def render(root: Path, *, to_stdout: bool = False) -> int:
    """生成并写入 `apisix.yaml`。

    Args:
        root: 仓库根。
        to_stdout: 是否同时打印生成内容。

    Returns:
        int: 退出码（0 成功）。
    """
    text = render_apisix_yaml()
    target = config_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if to_stdout:
        print(text, end="")
    else:
        print(f"[gateway_config] 已生成 {target}")
    return 0


def check(root: Path) -> int:
    """校验仓库内生成件与服务目录零漂移、服务发现无硬编码 IP、请求体上限三方一致。

    Args:
        root: 仓库根。

    Returns:
        int: 退出码（0 一致；1 缺失 / 漂移 / 硬编码 IP / 请求体上限口径不一致）。
    """
    target = config_path(root)
    if not target.is_file():
        print(f"[gateway_config] 缺失生成件：{target}（运行 render 生成）", file=sys.stderr)
        return 1
    if target.read_text(encoding="utf-8") != render_apisix_yaml():
        print(
            f"[gateway_config] 网关配置与服务目录不一致：{target}\n"
            "  运行 `uv run python -m ops.gateway_config render` 重新生成"
            "（来源：服务目录 SERVICE_CATALOG）",
            file=sys.stderr,
        )
        return 1
    violations = validate_service_discovery(render_apisix_config())
    if violations:
        print(
            f"[gateway_config] 服务发现校验失败（禁硬编码 IP）：{target}",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1
    body_size_problems = validate_body_size(root)
    if body_size_problems:
        print(
            f"[gateway_config] 请求体上限校验失败（三方一致 + 文件上传口径对齐）：{target}",
            file=sys.stderr,
        )
        for problem in body_size_problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        f"[gateway_config] 通过：{target} 与服务目录一致、服务发现无硬编码 IP、请求体上限三方一致且 ≥ 文件上传整包上限"
    )
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="生成 / 校验网关声明式配置（服务目录为单一来源）")
    parser.add_argument("command", choices=("render", "check"), help="render 生成；check 零漂移校验")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="仓库根（缺省自动定位）")
    parser.add_argument("--print", dest="to_stdout", action="store_true", help="render 时打印生成内容")
    args = parser.parse_args(argv)
    if args.command == "render":
        return render(args.root, to_stdout=args.to_stdout)
    return check(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
