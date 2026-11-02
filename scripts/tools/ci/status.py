"""CI 流水线状态查询（CLI）：一行看现状，并判断是否验证了最新提交。

为什么单独一个脚本：`watch_pipeline.py --once` 只打状态、不比对 `origin/main`，
容易把「旧流水线绿」读成「当前代码绿」（本仓推送**不触发**流水线，最新流水线常落后好几个提交）。

用法：
    python scripts/tools/ci/status.py                     # 最新流水线
    python scripts/tools/ci/status.py --pipeline 1481     # 指定流水线
    python scripts/tools/ci/status.py --jobs              # 展开 job 名（默认只给计数与失败/进行中）
    python scripts/tools/ci/status.py --json              # 输出 JSON
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trigger  # pyright: ignore[reportMissingImports]

_REPO_ROOT = Path(__file__).resolve().parents[3]
"""仓库根（`scripts/tools/ci/status.py` 上溯三层）。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# GitLab JSON 是动态结构（`json.loads` 结果无法静态表达），与 defect 脚本同口径。


def _get(api: str, token: str, path: str) -> Any:
    """GET 一个 API 路径（允许数组响应）。

    Args:
        api: API 基址。
        token: 访问令牌。
        path: 相对路径。

    Returns:
        Any: 解析后的 JSON。
    """
    req = urllib.request.Request(f"{api}/{path.lstrip('/')}", headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    return json.loads(payload) if payload else None


def _head_sha(ref: str = "origin/main") -> str:
    """取引用指向的短 sha（判断最新流水线是否验证了最新提交）。

    Args:
        ref: 分支引用。

    Returns:
        str: 9 位短 sha；取不到返回空串。
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short=9", ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def main(argv: Any = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 已取到；1 无流水线；2 用法 / 凭据问题）。
    """
    import argparse

    parser = argparse.ArgumentParser(description="查 CI 流水线状态（含「是否验证最新提交」判断）")
    parser.add_argument("--project", default="bms", help="仓短名（bms / mdm / engkit）")
    parser.add_argument("--pipeline", type=int, default=0, help="流水线 ID；0 表示最新")
    parser.add_argument("--jobs", action="store_true", help="展开全部 job 名")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    env = trigger.load_env(trigger.ENV_FILE)
    try:
        api = trigger.resolve("GITLAB_API_URL", env).rstrip("/")
        token = trigger.resolve("GITLAB_API_TOKEN", env)
        project_id = trigger.resolve_project_id(api, token, args.project, env)
    except (KeyError, ValueError) as exc:
        print(f"[失败] 缺少凭据：{exc}")
        return 2

    pipeline_id = args.pipeline
    if not pipeline_id:
        rows = _get(api, token, f"projects/{project_id}/pipelines?per_page=1")
        if not isinstance(rows, list) or not rows:
            print(f"{args.project}：没有流水线")
            return 1
        pipeline_id = int(rows[0]["id"])

    info = _get(api, token, f"projects/{project_id}/pipelines/{pipeline_id}")
    jobs = _get(api, token, f"projects/{project_id}/pipelines/{pipeline_id}/jobs?per_page=100")
    jobs = jobs if isinstance(jobs, list) else []

    counts: Any = {}
    names: Any = {}
    for job in jobs:
        state = str(job.get("status", "unknown"))
        if job.get("allow_failure") is True and state == "failed":
            state = "failed(allowed)"
        counts[state] = counts.get(state, 0) + 1
        names.setdefault(state, []).append(str(job.get("name", "")))

    pipeline_sha = str(info.get("sha", ""))
    head_sha = _head_sha()
    verified = bool(head_sha) and pipeline_sha.startswith(head_sha)
    result = {
        "project": args.project,
        "pipeline": pipeline_id,
        "status": info.get("status"),
        "ref": info.get("ref"),
        "sha": pipeline_sha[:9],
        "head_sha": head_sha,
        "verified_head": verified,
        "duration": info.get("duration"),
        "web_url": info.get("web_url"),
        "counts": counts,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(
        f"{args.project}#{pipeline_id} 状态={result['status']} 时长={result['duration']}s "
        f"ref={result['ref']} sha={result['sha']}"
    )
    print("计数：" + " / ".join(f"{state} {count}" for state, count in counts.items()))
    for state in ("failed", "failed(allowed)", "running", "pending"):
        if names.get(state):
            print(f"{state}：{', '.join(names[state])}")
    if args.jobs:
        for state, items in names.items():
            print(f"  [{state}] {', '.join(items)}")
    if head_sha and not verified:
        print(
            f"⚠ 该流水线验证的是 {pipeline_sha[:9]}，而 origin/main 已是 {head_sha}"
            "（本仓推送不触发流水线；需另起一轮才算验证最新代码）"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
