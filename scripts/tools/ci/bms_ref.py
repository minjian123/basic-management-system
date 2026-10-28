#!/usr/bin/env python3
"""bms 基座 ref 查看 / 钉版本（mdm CI 的 `BMS_REF` 项目变量）。

背景：mdm CI 的 `scripts/tools/ci/bms_setup.sh` **缺省 `BMS_REF=main`**——每次取 bms 远端 main 头，
日常无需人工维护；本脚本负责两件事：

1. `show`：打印 **bms 远端 main 头**、**bms 最新 `vX.Y.Z` 标签**、**目标项目当前 `BMS_REF` 值**；
2. `set`：把目标项目的 `BMS_REF` 写成指定值（`main` / `latest-tag` / 分支 / tag / SHA），或 `--clear`
   删除该变量回到「跟随 main 头」缺省。

用法::

    # 只看现状（缺省目标仓 = mdm）
    python3 scripts/tools/ci/bms_ref.py show

    # 钉到最新发布 tag / 指定 tag / 指定提交
    python3 scripts/tools/ci/bms_ref.py set --ref latest-tag
    python3 scripts/tools/ci/bms_ref.py set --ref v1.2.0
    python3 scripts/tools/ci/bms_ref.py set --ref 6a8038f12

    # 删除变量，回到缺省跟随 main 头
    python3 scripts/tools/ci/bms_ref.py set --clear

    # 只看将要发什么请求，不发
    python3 scripts/tools/ci/bms_ref.py set --ref v1.2.0 --dry-run

凭据与地址：与 `trigger.py` 同源——读仓根 `deploy/.env`（已 gitignore）的 `GITLAB_API_URL` /
`GITLAB_API_TOKEN` / `CI_PROJECT_ID`，也可用同名环境变量覆盖；`--project` 按项目路径名查项目 ID。
退出码：0 成功；1 请求失败 / 参数非法；2 用法或凭据缺失。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/ci/`）。"""

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_SRC_ROOT = ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from trigger import ENV_FILE, REPO_NAMES, load_env, request, resolve, resolve_project_id  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet  # noqa: E402

VARIABLE_KEY = "BMS_REF"
"""mdm CI 读取的基座 ref 变量名（`scripts/tools/ci/bms_setup.sh`）。"""

REF_CHOICES: ConcurrentStableSet[str] = ConcurrentStableSet(("main", "latest", "latest-tag"))
"""语义化取值（其余按分支 / tag / SHA 原样下发）。"""


def _git(args: ConcurrentStableList[str]) -> str:
    """执行 git（失败返回空串，由调用方决定是否告警）。

    Args:
        args: `git` 子命令与参数。

    Returns:
        str: 标准输出（去首尾空白）。
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), *args.to_list()],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _version_key(tag: str) -> ConcurrentStableList[int]:
    """标签 → 版本序键（`v1.2.10` > `v1.2.9`；非数字段按 0）。

    Args:
        tag: 标签名（如 `v1.2.0`）。

    Returns:
        ConcurrentStableList[int]: 版本序键（列表按字典序比较，可作 `sort` / `max` 键）。
    """
    parts: ConcurrentStableList[int] = ConcurrentStableList()
    for item in tag.lstrip("v").split("."):
        parts.add(int(item) if item.isdigit() else 0)
    return parts


def latest_local_tag() -> str:
    """取本仓可见的最新 `vX.Y.Z` 标签（离线可用的兜底口径）。

    Returns:
        str: 标签名；无标签为空串。
    """
    names = _git(ConcurrentStableList(["tag", "--list", "v*"]))
    if not names:
        return ""
    valid: ConcurrentStableList[str] = ConcurrentStableList()
    for name in names.splitlines():
        if name.startswith("v") and name[1:2].isdigit():
            valid.add(name)
    return max(valid, key=_version_key) if valid else ""


def _branch_head(api: str, token: str, project_id: str, branch: str) -> ConcurrentStableList[str]:
    """取远端分支头提交。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        branch: 分支名。

    Returns:
        ConcurrentStableList[str]: [提交短号, 提交时间]；取不到为空清单。
    """
    info = request(api, token, f"projects/{project_id}/repository/branches/{branch}")
    commit = info.get("commit")
    if not isinstance(commit, dict):
        return ConcurrentStableList()
    payload = ConcurrentStableDict(commit)
    return ConcurrentStableList(
        [str(payload.get("short_id") or payload.get("id") or ""), str(payload.get("committed_date") or "")]
    )


def _variable(api: str, token: str, project_id: str) -> str:
    """取项目变量现值。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。

    Returns:
        str: 变量值；未设置为空串。
    """
    try:
        info = request(api, token, f"projects/{project_id}/variables/{VARIABLE_KEY}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ""
        raise
    return str(info.get("value") or "")


def _upsert_variable(api: str, token: str, project_id: str, value: str) -> str:
    """写入项目变量（存在即更新、不存在即新建）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        value: 变量值。

    Returns:
        str: `updated` 或 `created`。
    """
    payload = ConcurrentStableDict({"value": value, "protected": False, "masked": False, "variable_type": "env_var"})
    path = f"projects/{project_id}/variables/{VARIABLE_KEY}"
    try:
        request(api, token, path, payload, method="PUT")
        return "updated"
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    request(api, token, path, payload, method="POST")
    return "created"


def _delete_variable(api: str, token: str, project_id: str) -> bool:
    """删除项目变量（不存在视为成功）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。

    Returns:
        bool: 实际删除为 True，原本不存在为 False。
    """
    try:
        request(api, token, f"projects/{project_id}/variables/{VARIABLE_KEY}", method="DELETE")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    return True


def _settings() -> ConcurrentStableList[str] | None:
    """取 API 基址与令牌（环境变量优先，其次 `deploy/.env`）。

    Returns:
        ConcurrentStableList[str] | None: [API 基址, 令牌]；缺失为 None。
    """
    env = load_env(ENV_FILE)
    api = resolve("GITLAB_API_URL", env)
    token = resolve("GITLAB_API_TOKEN", env)
    if not api or not token:
        print(f"[bms_ref] 缺少 GITLAB_API_URL / GITLAB_API_TOKEN（读 {ENV_FILE} 或同名环境变量）", file=sys.stderr)
        return None
    return ConcurrentStableList([api, token])


def cmd_show(project: str) -> int:
    """打印 bms ref 现状与目标项目变量。

    Args:
        project: 目标项目短名或路径（取 `BMS_REF` 现值）。

    Returns:
        int: 退出码。
    """
    settings = _settings()
    if settings is None:
        return 2
    api = settings[0]
    token = settings[1]
    env = load_env(ENV_FILE)
    bms_id = resolve_project_id(api, token, "bms", env)
    target_id = resolve_project_id(api, token, project, env)
    head = _branch_head(api, token, bms_id, "main")
    sha = head[0] if head else "（取不到）"
    committed = head[1] if len(head) > 1 else ""
    print(f"[bms_ref] bms 远端 main 头：{sha} {committed}".rstrip())
    print(f"[bms_ref] bms 本地可见最新 tag：{latest_local_tag() or '（无 vX.Y.Z 标签）'}")
    current = _variable(api, token, target_id)
    scope = REPO_NAMES.get(project, project)
    if current:
        print(f"[bms_ref] {scope} 的 {VARIABLE_KEY} = {current}")
    else:
        print(f"[bms_ref] {scope} 未设置 {VARIABLE_KEY} → 脚本缺省跟随 bms main 头")
    return 0


def cmd_set(project: str, ref: str, *, clear: bool, dry_run: bool) -> int:
    """写入 / 删除目标项目的 `BMS_REF`。

    Args:
        project: 目标项目短名或路径。
        ref: 取值（`main` / `latest` / `latest-tag` / 分支 / tag / SHA）。
        clear: 删除变量（回到缺省跟随 main 头）。
        dry_run: 只打印请求，不发。

    Returns:
        int: 退出码。
    """
    value = ref.strip()
    if not clear and not value:
        print("[bms_ref] set 需要 --ref <值> 或 --clear", file=sys.stderr)
        return 2
    settings = _settings()
    if settings is None:
        return 2
    api = settings[0]
    token = settings[1]
    env = load_env(ENV_FILE)
    target_id = resolve_project_id(api, token, project, env)
    scope = REPO_NAMES.get(project, project)
    if dry_run:
        action = "DELETE" if clear else f"PUT/POST {VARIABLE_KEY}={value}"
        print(f"[bms_ref] （dry-run）项目 {scope}（id={target_id}）→ {action}")
        return 0
    if clear:
        removed = _delete_variable(api, token, target_id)
        print(f"[bms_ref] {scope}：{'已删除' if removed else '原本未设置'} {VARIABLE_KEY} → 缺省跟随 bms main 头")
        return 0
    if value not in REF_CHOICES and not _looks_like_ref(value):
        print(f"[bms_ref] 提示：{value!r} 不是已知语义值，按分支 / tag / SHA 原样下发", file=sys.stderr)
    result = _upsert_variable(api, token, target_id, value)
    print(f"[bms_ref] {scope}：{VARIABLE_KEY}={value}（{result}）")
    return 0


def _looks_like_ref(value: str) -> bool:
    """粗判分支 / tag / SHA 形态（仅用于提示，不做拒绝）。

    Args:
        value: 待判定取值。

    Returns:
        bool: 命中 `v*` 标签、十六进制 SHA 或含字母的分支名。
    """
    if value.startswith("v") or len(value) >= 7:
        return True
    return any(ch.isalpha() for ch in value)


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 参数序列（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="查看 / 钉定 mdm CI 的 bms 基座 ref（BMS_REF）")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="打印 bms main 头 / 最新 tag 与目标项目 BMS_REF 现值")
    show.add_argument("--project", default="mdm", help="目标仓短名（bms / mdm / engkit）或 GitLab 项目路径")
    setter = sub.add_parser("set", help="写入或删除目标项目的 BMS_REF")
    setter.add_argument("--project", default="mdm", help="目标仓短名（bms / mdm / engkit）或 GitLab 项目路径")
    setter.add_argument("--ref", default="", help="取值：main / latest-tag / 分支 / tag / 提交 SHA")
    setter.add_argument("--clear", action="store_true", help="删除变量（回到缺省跟随 main 头）")
    setter.add_argument("--dry-run", action="store_true", help="只打印请求，不发")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    try:
        if args.command == "show":
            return cmd_show(str(args.project))
        return cmd_set(
            str(args.project),
            str(args.ref),
            clear=bool(args.clear),
            dry_run=bool(args.dry_run),
        )
    except urllib.error.HTTPError as exc:
        print(f"[bms_ref] GitLab API 失败：HTTP {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, ValueError) as exc:
        print(f"[bms_ref] 请求失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
