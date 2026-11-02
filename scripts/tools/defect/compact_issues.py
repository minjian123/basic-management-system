"""自动缺陷单收敛：关闭「已解决」的历史缺陷单。

背景：`defect-capture` 在流水线失败时按「含 commit 的摘要」算指纹，导致同一根因每轮都开新单，
且修复后无人关闭——实测积压 113 张 open 单、113 个互不相同的指纹。

判据（保守）：缺陷单的 commit **早于最近一次全绿流水线的 commit** ⇒ 该 commit 之后的全量流水线
已经全绿，失败在当前代码上不复现 ⇒ 视为已解决，关闭并留言说明依据。

用法：
    python scripts/tools/defect/compact_issues.py                # 只打印计划（dry-run）
    python scripts/tools/defect/compact_issues.py --apply        # 真正关闭
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# GitLab JSON 是动态结构（`json.loads` 结果无法静态表达），与本目录其它脚本同口径。

_ENV_FILE = Path(__file__).resolve().parents[3] / "deploy" / ".env"
"""凭据文件（本地运行时使用；CI 内走环境变量）。"""


def _env() -> Any:
    """取 GitLab 凭据：优先环境变量，其次 deploy/.env。

    Returns:
        Any: 含 `GITLAB_API_URL` / `GITLAB_API_TOKEN` / `CI_PROJECT_ID`。
    """
    out: Any = {
        "GITLAB_API_URL": os.environ.get("GITLAB_API_URL", ""),
        "GITLAB_API_TOKEN": os.environ.get("GITLAB_API_TOKEN", ""),
        "CI_PROJECT_ID": os.environ.get("CI_PROJECT_ID", ""),
    }
    if not all(out.values()) and _ENV_FILE.is_file():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key in out and not out[key]:
                out[key] = value.strip().strip('"').strip("'")
    return out


def _api(path: str, method: str = "GET", body: Any = None) -> Any:
    """调用 GitLab API。

    Args:
        path: 相对路径。
        method: HTTP 方法。
        body: JSON 载荷。

    Returns:
        Any: 解析后的响应（对象 / 数组 / None）。
    """
    env = _env()
    url = f"{env['GITLAB_API_URL'].rstrip('/')}/{path.lstrip('/')}"
    data = None
    if body is not None:
        import json

        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"PRIVATE-TOKEN": env["GITLAB_API_TOKEN"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    if not payload:
        return None
    import json

    return json.loads(payload)


def _last_green_sha(project: str) -> str:
    """取最近一次全绿流水线的 commit sha。

    Args:
        project: 项目 ID。

    Returns:
        str: 40 位 sha；取不到返回空串。
    """
    rows = _api(f"projects/{project}/pipelines?status=success&per_page=1")
    if isinstance(rows, list) and rows:
        return str(rows[0].get("sha", ""))
    return ""


def _is_ancestor(repo: Path, older: str, newer: str) -> bool | None:
    """判断 older 是否为 newer 的祖先（即「早于」）。

    Args:
        repo: 仓库目录。
        older: 候选较早 commit。
        newer: 参照 commit。

    Returns:
        bool | None: True 早于；False 不早于；None 本地无该 commit（无法判断）。
    """
    for sha in (older, newer):
        probe = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            return None
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _api_is_ancestor(project: str, older: str, newer: str) -> bool | None:
    """用 GitLab 的 merge_base 判断祖先关系（本地缺该 commit 时兜底）。

    Args:
        project: 项目 ID。
        older: 候选较早 commit。
        newer: 参照 commit。

    Returns:
        bool | None: True 早于；False 不早于（含无共同祖先）；None 服务端也判断不了。
    """
    try:
        merged = _api(f"projects/{project}/repository/merge_base?refs[]={older}&refs[]={newer}")
    except urllib.error.HTTPError as exc:
        # 404 "Merge Base Not Found" = 两者无共同祖先，即该 commit 不在主线历史上
        if exc.code == 404:
            return False
        return None
    except urllib.error.URLError, ValueError:
        return None
    if not isinstance(merged, dict):
        return None
    base = str(merged.get("id", ""))
    if not base:
        return None
    return base.startswith(older)


def _commit_exists(project: str, sha: str) -> bool:
    """该 commit 是否仍存在于服务端仓库。

    Args:
        project: 项目 ID。
        sha: commit sha。

    Returns:
        bool: 存在 True；404 或请求失败 False。
    """
    try:
        found = _api(f"projects/{project}/repository/commits/{sha}")
    except urllib.error.URLError, ValueError:
        return False
    return isinstance(found, dict) and bool(found.get("id"))


def _commit_of(issue: Any) -> str:
    """从缺陷单正文提取 commit。

    Args:
        issue: issue 对象。

    Returns:
        str: commit sha；无则空串。
    """
    import re

    matched = re.search(r"代码 commit：`([0-9a-f]{7,40})`", issue.get("description") or "")
    return matched.group(1) if matched else ""


def main(argv: Any = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 成功；2 用法 / 凭据问题）。
    """
    import argparse

    parser = argparse.ArgumentParser(description="收敛已解决的历史自动缺陷单")
    parser.add_argument("--apply", action="store_true", help="真正关闭（缺省只打印计划）")
    parser.add_argument("--repo-dir", default=str(_ENV_FILE.parents[1]), help="仓库目录")
    parser.add_argument("--label", default="defect-auto", help="缺陷单标签")
    parser.add_argument("--limit", type=int, default=500, help="最多处理多少张")
    args = parser.parse_args(argv)

    env = _env()
    if not (env["GITLAB_API_URL"] and env["GITLAB_API_TOKEN"] and env["CI_PROJECT_ID"]):
        print(f"[失败] 缺少凭据（GITLAB_API_URL / GITLAB_API_TOKEN / CI_PROJECT_ID，读 {_ENV_FILE}）")
        return 2
    project = env["CI_PROJECT_ID"]
    repo = Path(args.repo_dir)

    green = _last_green_sha(project)
    if not green:
        print("[失败] 取不到最近一次全绿流水线")
        return 2
    print(f"参照基线：最近一次全绿流水线 commit = {green[:9]}")

    label = urllib.parse.quote(args.label)
    issues: Any = []
    page = 1
    while len(issues) < args.limit:
        batch = _api(f"projects/{project}/issues?state=opened&labels={label}&per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        issues.extend(batch)
        page += 1

    closable: Any = []
    kept: Any = []
    for issue in issues:
        iid = int(issue.get("iid", 0))
        commit = _commit_of(issue)
        if not commit:
            kept.append((iid, "无 commit 字段", issue.get("title", "")))
            continue
        # 判据：只有「比最后全绿提交更新」的才算未解（需要保留）。
        # 绿流水线已覆盖它之前的全部代码，早于它的失败在当前代码上不复现；
        # 分叉 / 已 GC 的提交同理（其代码不在主线，失败无处复现）。
        newer = _is_ancestor(repo, green, commit)
        if newer is None:
            newer = _api_is_ancestor(project, green, commit)
        if newer is True:
            kept.append((iid, f"commit {commit[:9]} 晚于最后全绿提交", issue.get("title", "")))
        elif newer is False:
            closable.append((iid, commit[:9], issue.get("title", "")))
        elif not _commit_exists(project, commit):
            closable.append((iid, f"{commit[:9]}(已移除)", issue.get("title", "")))
        else:
            kept.append((iid, f"无法判定 commit {commit[:9]}", issue.get("title", "")))

    print(f"\n待关闭 {len(closable)} 张 / 保留 {len(kept)} 张（open 共 {len(issues)}）")
    for iid, sha, title in closable[:15]:
        print(f"  CLOSE #{iid:<5} {sha}  {title[:60]}")
    if len(closable) > 15:
        print(f"  …… 其余 {len(closable) - 15} 张同判据")
    for iid, why, title in kept[:10]:
        print(f"  KEEP  #{iid:<5} {why}  {title[:50]}")

    if not args.apply:
        print("\n[dry-run] 未执行任何变更；确认后加 --apply")
        return 0

    note = (
        f"自动收敛：本单 commit 早于最近一次全绿流水线（`{green[:9]}`），"
        f"该全量流水线已全部通过，失败在当前代码上不复现，故关闭。\n\n"
        f"若该问题仍存在，请重新触发失败流水线，新上报会附带失败 job / 失败用例 / 异常类型。"
    )
    closed = 0
    for iid, _sha, _title in closable:
        try:
            _api(f"projects/{project}/issues/{iid}/notes", "POST", {"body": note})
            _api(f"projects/{project}/issues/{iid}", "PUT", {"state_event": "close"})
            closed += 1
        except (urllib.error.URLError, ValueError) as exc:
            print(f"  [失败] #{iid}: {exc}")
    print(f"\n[完成] 已关闭 {closed} / {len(closable)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
