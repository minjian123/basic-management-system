"""CI 流水线 MCP 服务（stdio，仅标准库 + 仓库现有脚本）。

把 `scripts/tools/ci/` 已有的能力暴露为 MCP 工具，供编辑器 / Agent 直接调用：

| 工具 | 作用 |
| --- | --- |
| `ci_status` | 查最新或指定流水线的状态、job 分组、失败清单（秒查） |
| `ci_watch` | 盯守到终态或首个失败，只播报状态变化 |
| `ci_job_log` | 取指定 job 的日志尾部，并按优先级提取「失败要点」 |
| `ci_retry` | 重试流水线里失败的 job |
| `ci_trigger` | 触发新一轮流水线 |

**为什么需要**：脚本能力本身齐备，缺的是调用成本——每次要拼长命令行、把输出重定向到临时文件、
再人工判读。MCP 化后一次调用拿到结构化结果。

协议：stdin / stdout 每行一条 JSON-RPC 消息；**日志一律写 stderr**（stdout 只允许协议消息）。
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# MCP / GitLab 是 JSON 边界：载荷形状由外部协议决定（`json.loads` 结果无法静态表达），
# 故只对本文件放宽「未知类型」三条，其余类型检查照常。

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trigger  # pyright: ignore[reportMissingImports]

from bms_core.core.concurrent import ConcurrentStableDict

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "bms-ci"
SERVER_VERSION = "1.0.0"

_TERMINAL_STATUSES = frozenset({"success", "failed", "canceled", "skipped", "manual"})
"""流水线 / job 终态集合。"""

_PRIMARY_HINTS = (
    "[contract_gate]",
    "破坏性变更",
    "未达标",
    "FAILED ",
    "AssertionError",
    "Traceback (most recent call last)",
)
"""失败日志里优先提取的结论行关键字。"""

_NOISE_HINTS = ("Job failed: exit code", "warning", "WARNING", "instrumentation_skipped")
"""已知噪音（初始化告警 / 收尾行），不应冒充失败原因。"""


def _log(message: str) -> None:
    """写诊断日志（必须走 stderr，stdout 留给协议）。

    Args:
        message: 日志内容。
    """
    print(f"[bms-ci] {message}", file=sys.stderr, flush=True)


def _send(payload: Any) -> None:
    """输出一条 JSON-RPC 消息。

    Args:
        payload: 完整响应体。
    """
    print(json.dumps(payload, ensure_ascii=False), flush=True)


_REPO_ROOT = Path(__file__).resolve().parents[3]
"""仓库根（`scripts/tools/ci/mcp_server.py` 上溯三层）。"""


def _head_sha(ref: str = "origin/main") -> str:
    """取引用指向的提交短 sha，用于判断「最新流水线是否验证了最新提交」。

    本仓推送**不触发**流水线（需手工 `ci_trigger`），最新流水线常指向旧提交；
    不比对 sha 就会把「旧代码绿」当成「当前代码绿」——假绿灯。

    Args:
        ref: 分支引用（缺省 `origin/main`）。

    Returns:
        str: 9 位短 sha；取不到（无 git / 无该引用）返回空串。
    """
    import subprocess

    try:
        completed = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short=9", ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _api() -> tuple[str, str]:
    """解析 GitLab API 基址与令牌。

    Returns:
        tuple[str, str]: (api 基址, 访问令牌)。

    Raises:
        RuntimeError: 凭据缺失。
    """
    env = trigger.load_env(trigger.ENV_FILE)
    return (
        trigger.resolve("GITLAB_API_URL", env).rstrip("/"),
        trigger.resolve("GITLAB_API_TOKEN", env),
    )


def _http(api: str, token: str, path: str) -> Any:
    """GET 一个 API 路径（允许响应为对象或数组）。

    Args:
        api: API 基址。
        token: 访问令牌。
        path: 相对路径。

    Returns:
        Any: 解析后的响应体（dict / list）。

    Raises:
        RuntimeError: 请求失败。
    """
    url = f"{api}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"请求失败 {url}：{exc}") from exc
    return json.loads(raw) if raw else {}


def _project_id(api: str, token: str, project: str) -> str:
    """仓短名 → GitLab 项目 ID。

    Args:
        api: API 基址。
        token: 访问令牌。
        project: 仓短名（bms / mdm / engkit）。

    Returns:
        str: 项目 ID。
    """
    return trigger.resolve_project_id(api, token, project, trigger.load_env(trigger.ENV_FILE))


def _latest_pipeline_id(api: str, token: str, project_id: str) -> int:
    """取最新一条流水线 ID。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。

    Returns:
        int: 流水线 ID；没有流水线返回 0。
    """
    rows = _http(api, token, f"projects/{project_id}/pipelines?per_page=1")
    if not isinstance(rows, list) or not rows:
        return 0
    return int(rows[0].get("id", 0))


def _jobs(api: str, token: str, project_id: str, pipeline_id: int) -> Any:
    """取流水线的 job 列表（含 bridge）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        pipeline_id: 流水线 ID。

    Returns:
        list[dict[str, Any]]: job 行。
    """
    rows = _http(api, token, f"projects/{project_id}/pipelines/{pipeline_id}/jobs?per_page=100")
    return rows if isinstance(rows, list) else []


def _group(jobs: Any) -> Any:
    """按状态分组 job 名。

    Args:
        jobs: job 行。

    Returns:
        dict[str, list[str]]: 状态 → job 名清单。
    """
    grouped: Any = {}
    for job in jobs:
        state = str(job.get("status", "unknown"))
        if job.get("allow_failure") is True and state == "failed":
            state = "failed(allowed)"
        grouped.setdefault(state, []).append(str(job.get("name", "")))
    return grouped


def _job_trace(api: str, token: str, project_id: str, job_id: int) -> Any:
    """取 job 日志行（尾部若干行）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        job_id: job ID。

    Returns:
        list[str]: 日志行（取尾部 400 行）。
    """
    url = f"{api}/projects/{project_id}/jobs/{job_id}/trace"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"取日志失败：{exc}") from exc
    lines = text.splitlines()
    return lines[-400:]


def _failure_excerpt(api: str, token: str, project_id: str, job_id: int, tail: int) -> Any:
    """按关键字优先级提取失败要点（压到几行，不必点开整份日志）。

    Args:
        api: API 基址。
        token: 访问令牌。
        project_id: 项目 ID。
        job_id: job ID。
        tail: 返回行数上限。

    Returns:
        list[str]: 结论行。
    """
    lines = _job_trace(api, token, project_id, job_id)
    for hint in _PRIMARY_HINTS:
        hits = [line for line in lines if hint in line]
        if hits:
            return hits[-tail:]
    secondary = [
        line
        for line in lines
        if not any(noise in line for noise in _NOISE_HINTS)
        and any(k in line for k in ("error", "Error", "ERROR", "Exception", "assert", "failed"))
    ]
    return (secondary or lines)[-tail:]


def tool_ci_status(args: Any) -> str:
    """查流水线状态与 job 分组。

    Args:
        args: `project` / `pipeline`（0 表示最新）。

    Returns:
        str: 结构化文本结果。
    """
    project = str(args.get("project", "bms"))
    api, token = _api()
    project_id = _project_id(api, token, project)
    pipeline_id = int(args.get("pipeline", 0)) or _latest_pipeline_id(api, token, project_id)
    if not pipeline_id:
        return f"{project}：没有流水线"
    info = _http(api, token, f"projects/{project_id}/pipelines/{pipeline_id}")
    jobs = _jobs(api, token, project_id, pipeline_id)
    grouped = _group(jobs)
    failed = grouped.get("failed", [])
    pipeline_sha = str(info.get("sha", ""))
    head_sha = _head_sha()
    verified_head = bool(head_sha) and pipeline_sha.startswith(head_sha)
    brief: Any = {
        "project": project,
        "pipeline": pipeline_id,
        "status": info.get("status"),
        "ref": info.get("ref"),
        "sha": pipeline_sha[:9],
        "head_sha": head_sha,
        "verified_head": verified_head,
        "duration": info.get("duration"),
        "created_at": info.get("created_at"),
        "finished_at": info.get("finished_at"),
        "web_url": info.get("web_url"),
        "counts": {state: len(names) for state, names in grouped.items()},
        # 只展开「非成功」的 job 名（成功项给计数即可，避免把 38 个名字塞进上下文）
        "failed": failed,
        "running": grouped.get("running", []),
        "pending": grouped.get("pending", []),
    }
    lines = [
        f"{project}#{pipeline_id} 状态={brief['status']} 时长={brief['duration']}s "
        f"ref={brief['ref']} sha={brief['sha']}",
        "计数：" + " / ".join(f"{state} {count}" for state, count in brief["counts"].items()),
    ]
    if failed:
        lines.append("失败 job：" + ", ".join(failed))
    if brief["running"]:
        lines.append("进行中：" + ", ".join(brief["running"]))
    if head_sha and not verified_head:
        lines.append(
            f"⚠ 该流水线验证的是 {pipeline_sha[:9]}，而 origin/main 已是 {head_sha}"
            "（本仓推送不触发流水线；需用 ci_trigger 另起一轮才算验证最新代码）"
        )
    return "\n".join(lines) + "\n\n" + json.dumps(brief, ensure_ascii=False, indent=2)


def tool_ci_watch(args: Any) -> str:
    """盯守流水线，只播报状态变化；失败即给要点。

    Args:
        args: `project` / `pipeline` / `interval` / `fail_fast` / `timeout`。

    Returns:
        str: 变化播报与结论。
    """
    project = str(args.get("project", "bms"))
    interval = max(5, int(args.get("interval", 20)))
    fail_fast = bool(args.get("fail_fast", True))
    deadline = time.monotonic() + int(args.get("timeout", 600))
    api, token = _api()
    project_id = _project_id(api, token, project)
    pipeline_id = int(args.get("pipeline", 0)) or _latest_pipeline_id(api, token, project_id)
    if not pipeline_id:
        return f"{project}：没有流水线"

    seen: Any = {}
    announced: Any = set()
    out: Any = []
    while True:
        info = _http(api, token, f"projects/{project_id}/pipelines/{pipeline_id}")
        status = str(info.get("status"))
        jobs = _jobs(api, token, project_id, pipeline_id)
        for job in jobs:
            job_id = int(job.get("id", 0))
            state = str(job.get("status", ""))
            previous = seen.get(job_id)
            seen[job_id] = state
            if previous is not None and previous != state:
                out.append(f"  {job.get('name')}：{previous} → {state}（{job.get('duration')}s）")
            if state == "failed" and job.get("allow_failure") is not True and job_id not in announced:
                announced.add(job_id)
                out.append(f"  {job.get('name')} 失败要点：")
                for line in _failure_excerpt(api, token, project_id, job_id, 3):
                    out.append(f"    │ {line}")
                out.append(f"    job_id={job_id}（用 ci_job_log 取全文）")
                if fail_fast:
                    out.append(f"[结论] fail_fast：{project}#{pipeline_id} 已出现失败，提前返回")
                    return "\n".join(out)
        if status in _TERMINAL_STATUSES:
            out.append(f"[结论] {project}#{pipeline_id} 终态={status}")
            return "\n".join(out)
        if time.monotonic() >= deadline:
            out.append(f"[结论] 超时未到终态，当前={status}")
            return "\n".join(out)
        time.sleep(interval)


def tool_ci_job_log(args: Any) -> str:
    """取 job 日志尾部（可按关键字过滤）。

    Args:
        args: `project` / `job_id` / `grep` / `tail` / `excerpt`。

    Returns:
        str: 日志文本。
    """
    project = str(args.get("project", "bms"))
    job_id = int(args.get("job_id", 0))
    if not job_id:
        return "缺少 job_id"
    api, token = _api()
    project_id = _project_id(api, token, project)
    tail = int(args.get("tail", 60))
    if args.get("excerpt"):
        return "\n".join(_failure_excerpt(api, token, project_id, job_id, tail))
    lines = _job_trace(api, token, project_id, job_id)
    needle = str(args.get("grep", ""))
    if needle:
        lines = [line for line in lines if needle in line]
    return "\n".join(lines[-tail:])


def tool_ci_retry(args: Any) -> str:
    """重试流水线里失败的 job（需 `confirm=true`）。

    Args:
        args: `project` / `pipeline` / `confirm`。

    Returns:
        str: 执行结果。
    """
    if not args.get("confirm"):
        return "未执行：重试会真实触发 CI，需显式传 confirm=true"
    project = str(args.get("project", "bms"))
    pipeline_id = int(args.get("pipeline", 0))
    if not pipeline_id:
        return "缺少 pipeline"
    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "pipeline_retry.py"),
            f"{project}:{pipeline_id}",
            "--yes",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    return (completed.stdout or "") + (completed.stderr or "")


def tool_ci_trigger(args: Any) -> str:
    """触发新一轮流水线（需 `confirm=true`）。

    Args:
        args: `project` / `ref` / `confirm`。

    Returns:
        str: 触发结果。
    """
    if not args.get("confirm"):
        return "未执行：触发会真实起一轮 CI，需显式传 confirm=true"
    project = str(args.get("project", "bms"))
    ref = str(args.get("ref", "main"))
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "trigger.py"), "--project", project, "--ref", ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    return (completed.stdout or "") + (completed.stderr or "")


_TOOLS: ConcurrentStableDict[str, Any] = ConcurrentStableDict(
    {
        "ci_status": {
            "fn": tool_ci_status,
            "description": (
                "查 CI 流水线状态：返回状态/时长/web_url、按状态分组的 job、失败 job 清单。"
                "不知道 pipeline 号时传 0 取最新。用于「现在红没红」的秒查。"
            ),
            "schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "仓短名（bms/mdm/engkit），缺省 bms"},
                    "pipeline": {"type": "integer", "description": "流水线 ID；0 表示最新"},
                },
            },
        },
        "ci_watch": {
            "fn": tool_ci_watch,
            "description": (
                "盯守流水线直到终态或首个失败：只播报 job 状态变化，失败当场给「失败要点」（结论行，"
                "不是整份日志）。fail_fast=true 时一出现失败立即返回。适合推完代码后用。"
            ),
            "schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "pipeline": {"type": "integer", "description": "0 表示最新"},
                    "interval": {"type": "integer", "description": "轮询秒数，缺省 20"},
                    "fail_fast": {"type": "boolean", "description": "出现失败即返回，缺省 true"},
                    "timeout": {"type": "integer", "description": "总预算秒数，缺省 600"},
                },
            },
        },
        "ci_job_log": {
            "fn": tool_ci_job_log,
            "description": (
                "取指定 job 的日志：excerpt=true 时按关键字优先级只给结论行（推荐），"
                "否则给尾部若干行；grep 可二次过滤。"
            ),
            "schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "job_id": {"type": "integer"},
                    "grep": {"type": "string"},
                    "tail": {"type": "integer", "description": "返回行数，缺省 60"},
                    "excerpt": {"type": "boolean", "description": "只给失败要点"},
                },
                "required": ["job_id"],
            },
        },
        "ci_retry": {
            "fn": tool_ci_retry,
            "description": "重试流水线里所有失败 job。有副作用，必须传 confirm=true。",
            "schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "pipeline": {"type": "integer"},
                    "confirm": {"type": "boolean"},
                },
                "required": ["pipeline", "confirm"],
            },
        },
        "ci_trigger": {
            "fn": tool_ci_trigger,
            "description": "触发新一轮流水线。有副作用，必须传 confirm=true。",
            "schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "ref": {"type": "string", "description": "分支，缺省 main"},
                    "confirm": {"type": "boolean"},
                },
                "required": ["confirm"],
            },
        },
    }
)


def _tool_list() -> Any:
    """生成 `tools/list` 的响应体。

    Returns:
        list[dict[str, Any]]: 工具描述数组。
    """
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["schema"],
        }
        for name, spec in _TOOLS.items()
    ]


def _call_tool(name: str, args: Any) -> Any:
    """执行一个工具。

    Args:
        name: 工具名。
        args: 入参。

    Returns:
        tuple[str, bool]: (文本结果, 是否错误)。
    """
    spec = _TOOLS.get(name)
    if spec is None:
        return f"未知工具：{name}", True
    try:
        return str(spec["fn"](args)), False
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}", True


def _handle(request: Any) -> Any:
    """处理一条 JSON-RPC 请求。

    Args:
        request: 请求体。

    Returns:
        dict[str, Any] | None: 响应体（通知类消息返回 None）。
    """
    method = str(request.get("method", ""))
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": _tool_list()}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        text, is_error = _call_tool(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
        }
    _log(f"未支持的方法：{method}")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    """stdio 主循环。

    Returns:
        int: 退出码。
    """
    _log(f"{SERVER_NAME} {SERVER_VERSION} 已启动（stdio）")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _log("收到非 JSON 行，已忽略")
            continue
        try:
            response = _handle(request)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": str(exc)},
            }
        if response is not None:
            _send(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
