#!/usr/bin/env python3
"""CI 配置校验（跨仓）：按仓短名或文件路径校验 `.gitlab-ci.yml` 能否被 GitLab 接受。

优先走 GitLab CI Lint API——与流水线同一解析器，`rules` / 关键词 / `include` 等语义错误都能查出来；
网络或凭据不可用时回落本地 YAML 解析（只查语法与标签可解析性），也可用 `--local` 显式只跑本地。

用法::

    # 校验三个仓的 .gitlab-ci.yml（本地 YAML + API）
    python3 scripts/tools/ci/lint_ci.py bms mdm engkit

    # 校验任意路径的文件（文件在某个平级仓目录下时同样走该仓的 API 校验）
    python3 scripts/tools/ci/lint_ci.py --file deploy/ci/templates/backend-service.yml

    # 离线：只做本地 YAML 解析
    python3 scripts/tools/ci/lint_ci.py mdm --local

    # 机器可读
    python3 scripts/tools/ci/lint_ci.py bms --json

凭据与地址：与 `trigger.py` 同源——读仓根 `deploy/.env`（已 gitignore）的 `GITLAB_API_URL` /
`GITLAB_API_TOKEN`，也可用同名环境变量覆盖；公开仓无凭据时自动只跑本地。
退出码：0 全部通过；1 存在校验失败；2 用法错误（仓名未知 / 文件不存在）。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/ci/`）。"""

WORKSPACE = ROOT.parent
"""工作区根（`bms/` 的父目录，各平级仓在其下）。"""

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_SRC_ROOT = ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from trigger import ENV_FILE, REPO_NAMES, load_env, resolve  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402

API_TIMEOUT_SECONDS = 30
"""单次 GitLab API 调用超时（秒）。"""

DEFAULT_CONFIG_NAME = ".gitlab-ci.yml"
"""仓根默认校验的 CI 配置文件。"""


def _split(values: ConcurrentStableList[str] | None) -> ConcurrentStableList[str]:
    """把可重复 / 逗号分隔的参数拍平（保序去重）。

    Args:
        values: 原始参数（可为 None）。

    Returns:
        ConcurrentStableList[str]: 拍平后的取值。
    """
    flattened: ConcurrentStableList[str] = ConcurrentStableList()
    for value in values or ():
        for item in value.split(","):
            name = item.strip()
            if name and name not in flattened:
                flattened.append(name)
    return flattened


def _project_of(path: Path) -> str:
    """由文件路径反查所属平级仓的 GitLab 项目路径。

    Args:
        path: 待校验文件路径。

    Returns:
        str: 项目路径（不在任何已登记平级仓下时为空串，表示只做本地校验）。
    """
    try:
        relative = path.resolve().relative_to(WORKSPACE)
    except ValueError:
        return ""
    return REPO_NAMES.get(relative.parts[0], "") if relative.parts else ""


def _local_errors(path: Path) -> ConcurrentStableList[str] | None:
    """本地 YAML 解析（GitLab 的 `!reference` 等自定义标签按空值处理，不误报）。

    Args:
        path: 待校验文件路径。

    Returns:
        ConcurrentStableList[str] | None: 错误列表；本机无 pyyaml 时返回 None（表示跳过）。
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return None
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"读取失败：{exc}")
        return errors

    class _GitLabLoader(yaml.SafeLoader):
        """把 GitLab 私有标签（`!reference` 等）当普通标量，只校验语法与结构。"""

    _GitLabLoader.add_multi_constructor("!", lambda loader, suffix, node: None)
    try:
        yaml.load(text, Loader=_GitLabLoader)  # SafeLoader 派生，只做语法与结构校验
    except yaml.YAMLError as exc:
        errors.append(" ".join(str(exc).split()))
    return errors


def _api_errors(
    api: str,
    token: str,
    project: str,
    content: str,
    ref: str,
) -> tuple[bool, ConcurrentStableList[str]]:
    """调 GitLab CI Lint API（`POST /projects/:id/ci/lint`）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project: GitLab 项目路径（如 `bms/bms`）。
        content: 待校验的 CI 配置全文。
        ref: 解析 `include` 等相对引用时使用的 ref。

    Returns:
        tuple[bool, ConcurrentStableList[str]]: 是否有效与错误列表。
    """
    quoted = urllib.parse.quote(project, safe="")
    payload = json.dumps({"content": content, "ref": ref}).encode()
    url = f"{api.rstrip('/')}/projects/{quoted}/ci/lint"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
        data: object = json.loads(resp.read().decode("utf-8", "replace"))
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    if not isinstance(data, dict):
        errors.append("Lint API 响应非法")
        return False, errors
    for item in data.get("errors") or ():
        errors.append(str(item))
    return bool(data.get("valid")), errors


def _resolve_targets(
    projects: ConcurrentStableList[str],
    files: ConcurrentStableList[str],
) -> ConcurrentStableList[tuple[str, Path]]:
    """把参数解析成「标签 + 文件路径」列表。

    Args:
        projects: 仓短名列表。
        files: 显式文件路径列表。

    Returns:
        ConcurrentStableList[tuple[str, Path]]: 校验目标（保序去重）。

    Raises:
        ValueError: 仓短名未登记。
    """
    targets: ConcurrentStableList[tuple[str, Path]] = ConcurrentStableList()
    for name in projects:
        if name not in REPO_NAMES:
            known = " / ".join(REPO_NAMES)
            raise ValueError(f"未知仓短名：{name}（可用：{known}）")
        target = (name, WORKSPACE / name / DEFAULT_CONFIG_NAME)
        if target not in targets:
            targets.append(target)
    for raw in files:
        path = Path(raw)
        target = (raw, path if path.is_absolute() else Path.cwd() / path)
        if target not in targets:
            targets.append(target)
    return targets


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 全通过 / 1 存在失败 / 2 用法错误）。
    """
    parser = argparse.ArgumentParser(description="CI 配置校验（跨仓：本地 YAML + GitLab Lint API）")
    parser.add_argument("projects", nargs="*", help="仓短名（bms / mdm / engkit / biz / test），可多个或逗号分隔")
    parser.add_argument("--file", action="append", default=None, help="显式校验某个文件（可重复或逗号分隔）")
    parser.add_argument("--ref", default="main", help="Lint 使用的 ref（缺省 main，用于解析 include 等相对引用）")
    parser.add_argument("--local", action="store_true", help="只做本地 YAML 解析，不请求 API")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    try:
        targets = _resolve_targets(
            _split(ConcurrentStableList(args.projects)), _split(ConcurrentStableList(args.file or ()))
        )
    except ValueError as exc:
        print(f"[lint] {exc}", file=sys.stderr)
        return 2
    if not targets:
        print("[lint] 缺少校验目标：给仓短名（bms / mdm / engkit）或 --file <路径>", file=sys.stderr)
        return 2

    env = load_env(ENV_FILE)
    api = "" if args.local else resolve("GITLAB_API_URL", env)
    token = "" if args.local else resolve("GITLAB_API_TOKEN", env)
    if not args.local and (not api or not token):
        print(
            "[lint] 缺少 GITLAB_API_URL / GITLAB_API_TOKEN，只做本地 YAML 解析（可用 --local 显式声明）",
            file=sys.stderr,
        )
        api = ""
        token = ""

    failed = False
    summary: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for label, path in targets:
        if not path.is_file():
            print(f"[lint] {label} 文件不存在：{path}", file=sys.stderr)
            return 2
        local = _local_errors(path)
        local_state = "skip" if local is None else ("ok" if not local else "invalid")
        api_state = "skip"
        api_errors: ConcurrentStableList[str] = ConcurrentStableList()
        if api and token:
            project = _project_of(path)
            content = path.read_text(encoding="utf-8")
            if project:
                try:
                    valid, api_errors = _api_errors(api, token, project, content, str(args.ref))
                    api_state = "ok" if valid else "invalid"
                except urllib.error.HTTPError as exc:
                    api_state = f"error HTTP {exc.code}"
                except urllib.error.URLError as exc:
                    api_state = f"error {exc.reason}"
            else:
                api_state = "skip（不在已登记平级仓下）"
        errors = ConcurrentStableList[str]()
        if local:
            errors.extend(local)
        errors.extend(api_errors)
        print(f"[lint] {label}  yaml={local_state}  api={api_state}")
        for line in errors:
            print(f"[lint]   - {line}")
        if local_state == "invalid" or api_state == "invalid" or api_state.startswith("error"):
            failed = True
        summary.append(
            ConcurrentStableDict(
                {
                    "target": label,
                    "path": str(path),
                    "yaml": local_state,
                    "api": api_state,
                    "errors": tuple(errors),
                },
            ),
        )

    if args.json:
        print(json.dumps([dict(item) for item in summary], ensure_ascii=False, indent=2))
    print(f"[lint] 结论：{'存在失败' if failed else '全部通过'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
