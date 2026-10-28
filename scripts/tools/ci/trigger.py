#!/usr/bin/env python3
"""手工触发 CI 流水线（推送不再触发流水线的配套入口）。

背景（2026-10-26 用户拍板）：`workflow.rules` 已去掉 `push` / `merge_request_event`——**推送一律不建
流水线**（因此推送**无需**再加 `-o ci.skip`）；CI 改为**按需手工触发**，且**手工触发即全量**（无 Git
推送事件的流水线里 `rules:changes` 恒为真，各 job 天然全跑）。本脚本是这条口径的便捷入口，免手敲
curl 与 token 拼装。

用法::

    # 触发 bms 的 main（缺省仓 = 本脚本所在仓）
    python3 scripts/tools/ci/trigger.py

    # 触发指定仓 / 分支 / tag
    python3 scripts/tools/ci/trigger.py --project mdm --ref main
    python3 scripts/tools/ci/trigger.py --ref v1.2.0

    # 只看将要发什么请求，不发
    python3 scripts/tools/ci/trigger.py --dry-run

    # 触发后盯到终态（缺省只打印流水线地址就返回）
    python3 scripts/tools/ci/trigger.py --watch

凭据与地址：读仓根 `deploy/.env`（已 gitignore）的 `GITLAB_API_URL` / `GITLAB_API_TOKEN` /
`CI_PROJECT_ID`，也可用同名环境变量覆盖；`--project` 按项目路径名查项目 ID（需 token 有 api 权限）。
退出码：0 已受理（`--watch` 时为终态 success）；1 请求失败 / 流水线终态非 success；2 用法或凭据缺失。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/ci/`）。"""

_SRC_ROOT = ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402

ENV_FILE = ROOT / "deploy" / ".env"
"""凭据文件（gitignore；键位见 `deploy/.env.example`）。"""

REPO_NAMES: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "bms": "bms/bms",
        "mdm": "mjs/mdm",
        "engkit": "bms/engkit",
        "biz": "mjs/biz",
        "test": "bms/test",
    }
)
"""`--project` 短名 → GitLab 项目路径（与实际 GitLab 项目路径一致；新仓在此登记，也可直接传路径）。"""

TERMINAL_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(["success", "failed", "canceled", "skipped"])
"""流水线终态集合。"""


def load_env(path: Path) -> ConcurrentStableDict[str, str]:
    """读取 `KEY=VALUE` 形式的环境文件（不存在时返回空）。

    Args:
        path: 环境文件路径。

    Returns:
        ConcurrentStableDict[str, str]: 键值表。
    """
    values: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values.set(key.strip(), value.strip().strip('"').strip("'"))
    return values


def resolve(key: str, env: ConcurrentStableDict[str, str]) -> str:
    """取配置：环境变量优先，其次 `deploy/.env`。

    Args:
        key: 键名。
        env: 环境文件键值表。

    Returns:
        str: 配置值（缺失为空串）。
    """
    return os.environ.get(key, "").strip() or env.get(key, "")


def request(
    api: str,
    token: str,
    path: str,
    payload: ConcurrentStableDict[str, object] | None = None,
    *,
    method: str | None = None,
) -> ConcurrentStableDict[str, object]:
    """调用 GitLab API（JSON 进出）。

    Args:
        api: API 基址（如 `http://<host>:8080/api/v4`）。
        token: 访问令牌。
        path: 相对 API 基址的路径（如 `projects/2/pipeline`）。
        payload: 请求载荷（None 表示无体）。
        method: HTTP 方法；缺省按载荷推导（有体 POST、无体 GET）。变量读改删用 GET / PUT / POST / DELETE。

    Returns:
        ConcurrentStableDict[str, object]: 解析后的响应体（204 无体返回空映射）。
    """
    url = f"{api.rstrip('/')}/{path.lstrip('/')}"
    body = None if payload is None else json.dumps(dict(payload)).encode()
    verb = method or ("GET" if body is None else "POST")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
        method=verb,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    if not raw:
        return ConcurrentStableDict()
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"响应不是对象：{url}")
    return ConcurrentStableDict(cast("dict[str, object]", parsed))


def resolve_project_id(api: str, token: str, project: str, env: ConcurrentStableDict[str, str]) -> str:
    """解析项目 ID：本仓（缺省）用 `CI_PROJECT_ID`，其他仓按项目路径查。

    Args:
        api: API 基址。
        token: 访问令牌。
        project: 短名或 GitLab 项目路径。
        env: 环境文件键值表。

    Returns:
        str: 项目 ID（数字串）。
    """
    name = project.strip()
    if name in ("", "bms"):
        project_id = resolve("CI_PROJECT_ID", env)
        if project_id:
            return project_id
    path = REPO_NAMES.get(name, name)
    quoted = urllib.parse.quote(path, safe="")
    info = request(api, token, f"projects/{quoted}")
    raw = info.get("id")
    if not isinstance(raw, int):
        raise ValueError(f"项目查询未返回 id：{path}")
    return str(raw)


def trigger(api: str, token: str, project_id: str, ref: str) -> ConcurrentStableDict[str, object]:
    """创建流水线（`POST /projects/:id/pipeline`）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        ref: 分支名或 tag 名。

    Returns:
        ConcurrentStableDict[str, object]: 流水线对象（含 `id` / `web_url` / `status`）。
    """
    return request(api, token, f"projects/{project_id}/pipeline", ConcurrentStableDict({"ref": ref}))


def watch(api: str, token: str, project_id: str, pipeline_id: int, interval: int) -> str:
    """轮询到流水线终态。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        pipeline_id: 流水线 ID。
        interval: 轮询间隔（秒）。

    Returns:
        str: 终态状态。
    """
    status = "created"
    while status not in TERMINAL_STATUSES:
        time.sleep(interval)
        current = request(api, token, f"projects/{project_id}/pipelines/{pipeline_id}")
        raw = current.get("status")
        status = raw if isinstance(raw, str) else "unknown"
        print(f"[trigger] 流水线 #{pipeline_id} 状态：{status}", flush=True)
        if status in TERMINAL_STATUSES:
            break
    return status


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 已受理 / 1 请求或终态失败 / 2 用法或凭据缺失）。
    """
    parser = argparse.ArgumentParser(description="手工触发 CI 流水线（推送不再触发，CI 按需全量跑）")
    parser.add_argument("--project", default="bms", help="仓短名（bms / mdm / engkit）或 GitLab 项目路径")
    parser.add_argument("--ref", default="main", help="分支名或 tag 名（缺省 main）")
    parser.add_argument("--dry-run", action="store_true", help="只打印请求，不发")
    parser.add_argument("--watch", action="store_true", help="触发后轮询到终态")
    parser.add_argument("--interval", type=int, default=20, help="--watch 的轮询间隔秒数（缺省 20）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    env = load_env(ENV_FILE)
    api = resolve("GITLAB_API_URL", env)
    token = resolve("GITLAB_API_TOKEN", env)
    if not api or not token:
        print(f"[trigger] 缺少 GITLAB_API_URL / GITLAB_API_TOKEN（读 {ENV_FILE} 或同名环境变量）", file=sys.stderr)
        return 2

    try:
        project_id = resolve_project_id(api, token, str(args.project), env)
    except (urllib.error.URLError, ValueError) as exc:
        print(f"[trigger] 解析项目失败：{exc}", file=sys.stderr)
        return 1
    url = f"{api.rstrip('/')}/projects/{project_id}/pipeline"
    if args.dry_run:
        print(f"[trigger] 将 POST {url} 载荷 {{'ref': {args.ref!r}}}（dry-run，未发送）")
        return 0

    try:
        pipeline = trigger(api, token, project_id, str(args.ref))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"[trigger] 创建流水线失败（HTTP {exc.code}）：{detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"[trigger] 创建流水线失败（网络不可达）：{exc}", file=sys.stderr)
        return 1

    raw_id = pipeline.get("id")
    pipeline_id = raw_id if isinstance(raw_id, int) else 0
    web_url = str(pipeline.get("web_url", ""))
    print(f"[trigger] 已触发流水线 #{pipeline_id}（ref={args.ref}）")
    if web_url:
        print(f"[trigger] 地址：{web_url}")
    if not args.watch:
        return 0
    status = watch(api, token, project_id, pipeline_id, max(5, int(args.interval)))
    print(f"[trigger] 流水线 #{pipeline_id} 终态：{status}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
