"""watch-pipeline.py - GitLab 流水线盯守：低频轮询到终态即退出，逐拍进度可查

用法:
    python watch-pipeline.py --pipeline-id 29 [--project 2] [--timeout 600] [--interval 15]
                             [--stall-seconds 0] [--max-failures 5] [--quiet]

行为:
    - 终态（success / failed / canceled / skipped）即退出：0 成功、1 非成功、2 超时。
    - 逐拍进度（默认开，--quiet 关）：每拍输出「时间 / status / 运行中 job / 失败 job」，
      经 bg_status 可见实时进度与卡点，不再等到终态才有输出。
    - API 容错：mjbk 繁忙 / 不可达时记 API_UNREACHABLE 并续跑，连续失败超 --max-failures
      以退出码 3 结束（不静默死等、不崩溃）。
    - 卡住提示：某 job 运行超过 --stall-seconds（>0 生效）输出 PIPELINE_STALL_HINT
      （含 job 名与已运行时长），供人工介入。

凭据读 deploy/.env 的 GITLAB_API_URL / GITLAB_API_TOKEN。
配合 bg 工具使用：bg-run 包装本脚本，bg-status/bg-wait 查询结果。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = _REPO_ROOT / "deploy" / ".env"  # deploy/.env

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (  # noqa: E402
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)

TERMINAL = ("success", "failed", "canceled", "skipped")
"""流水线终态集合（skipped：全 job 跳过亦为终态，不再等到超时）。"""

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_TIMEOUT = 2
EXIT_API_UNREACHABLE = 3


def load_env() -> ConcurrentStableDict[str, str]:
    """读取 deploy/.env 为键值映射（缺失返回空）。

    Returns:
        ConcurrentStableDict[str, str]: 环境变量映射。
    """
    env: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if not ROOT.exists():
        return env
    for line in ROOT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env.set(k.strip(), v.strip())
    return env


def _api_get(url: str, token: str, timeout: int) -> object:
    """GET 一个 GitLab API 端点并解析 JSON（失败抛异常，由调用方处置）。

    Args:
        url: 完整端点 URL。
        token: 私有令牌。
        timeout: 单请求超时（秒）。

    Returns:
        object: 解析后的 JSON。
    """
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _job_names(jobs: object, status: str) -> ConcurrentStableList[str]:
    """筛出指定状态的 job 名（含前缀 stage）。

    Args:
        jobs: jobs 端点返回（列表）。
        status: 目标状态（running / failed）。

    Returns:
        ConcurrentStableList[str]: 命中的 `stage:name` 列表。
    """
    names: ConcurrentStableList[str] = ConcurrentStableList()
    if not isinstance(jobs, list):
        return names
    for job in jobs:
        if isinstance(job, dict) and job.get("status") == status:
            names.add(f"{job.get('stage', '?')}:{job.get('name', '?')}")
    return names


def _running_elapsed(jobs: object) -> ConcurrentStableDict[str, float]:
    """计算各运行中 job 的已运行秒数（用于卡住提示）。

    Args:
        jobs: jobs 端点返回（列表）。

    Returns:
        ConcurrentStableDict[str, float]: `job名 → 已运行秒数`（无法解析起始时间则跳过）。
    """
    elapsed: ConcurrentStableDict[str, float] = ConcurrentStableDict()
    if not isinstance(jobs, list):
        return elapsed
    now = datetime.now(UTC)
    for job in jobs:
        if not (isinstance(job, dict) and job.get("status") == "running"):
            continue
        started = job.get("started_at")
        if not isinstance(started, str):
            continue
        try:
            began = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except ValueError:
            continue
        name = str(job.get("name", "?"))
        elapsed.set(name, (now - began).total_seconds())
    return elapsed


def _fmt(names: ConcurrentStableList[str]) -> str:
    """格式化 job 名列表。

    Args:
        names: job 名列表。

    Returns:
        str: `[a,b]` 或 `[]`。
    """
    return "[" + ",".join(names) + "]"


def main() -> int:
    """盯守入口：轮询到终态 / 超时 / API 连续不可达。

    Returns:
        int: 0 成功 / 1 非成功终态 / 2 超时 / 3 API 连续不可达。
    """
    parser = argparse.ArgumentParser(description="GitLab 流水线盯守")
    parser.add_argument("--pipeline-id", type=int, required=True)
    parser.add_argument("--project", type=int, default=2, help="项目 ID（默认 bms/bms = 2）")
    parser.add_argument("--timeout", type=int, default=600, help="等待上限秒数（默认 600）")
    parser.add_argument("--interval", type=int, default=15, help="轮询间隔秒数（默认 15）")
    parser.add_argument(
        "--stall-seconds",
        type=int,
        default=0,
        help="job 运行超此秒数提示卡住（0=关，默认 0）",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=5,
        help="API 连续失败上限（默认 5，超则以码 3 退出）",
    )
    parser.add_argument("--quiet", action="store_true", help="只输出终态（关闭逐拍进度）")
    args = parser.parse_args()

    env = load_env()
    env.update((k, v) for k, v in os.environ.items() if k.startswith(("GITLAB_API", "CI_PROJECT_ID")))
    api = env.get("GITLAB_API_URL")
    token = env.get("GITLAB_API_TOKEN")
    if not (api and token):
        print("缺少 GITLAB_API_URL / GITLAB_API_TOKEN（deploy/.env 或环境变量）")
        return EXIT_FAILED

    base = api.rstrip("/")
    pipeline_url = f"{base}/projects/{args.project}/pipelines/{args.pipeline_id}"
    jobs_url = f"{pipeline_url}/jobs?per_page=100"
    deadline = time.time() + args.timeout
    warned: ConcurrentStableSet[str] = ConcurrentStableSet()
    failures = 0
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    while True:
        stamp = time.strftime("%H:%M:%S")
        try:
            raw_pipeline = _api_get(pipeline_url, token, 10)
            data = ConcurrentStableDict(raw_pipeline if isinstance(raw_pipeline, dict) else {})
            failures = 0
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            failures += 1
            if not args.quiet:
                print(
                    f"[{stamp}] API_UNREACHABLE {failures}/{args.max_failures}（{exc!r}）",
                    flush=True,
                )
            if failures >= args.max_failures:
                print(
                    f"PIPELINE_API_UNREACHABLE pipeline={args.pipeline_id} failures={failures} "
                    f"（mjbk 可能繁忙或不可达，请检查服务器后重试）"
                )
                return EXIT_API_UNREACHABLE
            time.sleep(args.interval)
            continue

        status = str(data.get("status", "unknown"))
        running: ConcurrentStableList[str] = ConcurrentStableList()
        failed_jobs: ConcurrentStableList[str] = ConcurrentStableList()
        elapsed: ConcurrentStableDict[str, float] = ConcurrentStableDict()
        try:
            jobs = _api_get(jobs_url, token, 10)
            running = _job_names(jobs, "running")
            failed_jobs = _job_names(jobs, "failed")
            elapsed = _running_elapsed(jobs)
        except urllib.error.URLError, TimeoutError, OSError, ValueError:
            pass  # job 明细是增强信息，取不到不阻断盯守

        if not args.quiet:
            print(
                f"[{stamp}] status={status} running={_fmt(running)} failed={_fmt(failed_jobs)}",
                flush=True,
            )

        if args.stall_seconds > 0:
            for job_name, seconds in elapsed.items():
                if seconds >= args.stall_seconds and job_name not in warned:
                    warned.add(job_name)
                    print(
                        f"PIPELINE_STALL_HINT job={job_name} running={int(seconds)}s "
                        f"（超过 {args.stall_seconds}s 阈值，疑似卡住 / 重活）",
                        flush=True,
                    )

        if status in TERMINAL:
            break
        if time.time() >= deadline:
            print(f"PIPELINE_WAIT_TIMEOUT pipeline={args.pipeline_id} status={status}")
            return EXIT_TIMEOUT
        time.sleep(args.interval)

    ref = data.get("ref", "")
    sha = str(data.get("sha") or "")[:8]
    print(f"FINAL: pipeline {args.pipeline_id} [{ref} @{sha}] status={status} web_url={data.get('web_url', '')}")
    return EXIT_SUCCESS if status == "success" else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
