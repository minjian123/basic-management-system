"""watch-pipeline.py - GitLab 流水线盯守：轮询到终态（success/failed/canceled）即退出

用法:
    python watch-pipeline.py --pipeline-id 29 [--project 2] [--timeout 600] [--interval 15]

凭据读 deploy/.env 的 GITLAB_API_URL / GITLAB_API_TOKEN。
配合 bg 工具使用：bg-run 包装本脚本，bg-wait/bg-status 查询结果。
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = _REPO_ROOT / "deploy" / ".env"  # deploy/.env

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableDict  # noqa: E402


def load_env() -> ConcurrentStableDict[str, str]:
    env: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if not ROOT.exists():
        return env
    for line in ROOT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env.set(k.strip(), v.strip())
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="GitLab 流水线盯守")
    parser.add_argument("--pipeline-id", type=int, required=True)
    parser.add_argument("--project", type=int, default=2, help="项目 ID（默认 bms/bms = 2）")
    parser.add_argument("--timeout", type=int, default=600, help="等待上限秒数（默认 600）")
    parser.add_argument("--interval", type=int, default=15, help="轮询间隔秒数（默认 15）")
    args = parser.parse_args()

    env = load_env()
    env.update((k, v) for k, v in __import__("os").environ.items() if k.startswith(("GITLAB_API", "CI_PROJECT_ID")))
    api = env.get("GITLAB_API_URL")
    token = env.get("GITLAB_API_TOKEN")
    if not (api and token):
        print("缺少 GITLAB_API_URL / GITLAB_API_TOKEN（deploy/.env 或环境变量）")
        return 1

    url = f"{api.rstrip('/')}/projects/{args.project}/pipelines/{args.pipeline_id}"
    deadline = time.time() + args.timeout
    status = "unknown"
    while True:
        req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        status = data["status"]
        if status in ("success", "failed", "canceled"):
            break
        if time.time() >= deadline:
            print(f"PIPELINE_WAIT_TIMEOUT pipeline={args.pipeline_id} status={status}")
            return 2
        time.sleep(args.interval)

    ref = data.get("ref", "")
    sha = (data.get("sha") or "")[:8]
    print(f"FINAL: pipeline {args.pipeline_id} [{ref} @{sha}] status={status} web_url={data.get('web_url', '')}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
