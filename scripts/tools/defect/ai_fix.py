"""AI 缺陷修复代理（双轨：本地模型优先，云端兜底；AI 提 MR、人工合入）。

流程（对应《测试规范》9 节自动上报的后续环节）:
  1. 扫描 GitLab 未关闭 defect-auto 标签 Issue（或 --issue 指定单个）
  2. 从 Issue 描述提取 REPRO 复现包路径，读取 repro.json / REPRO.md / stacktrace.txt
  3. 组装上下文（堆栈 + 失败测试文件 + 相关源码），先交本地模型（LM Studio）辨识定位：
     - 本地可定位且置信度高 -> 生成 unified diff
     - 本地失败/置信度低 且 AI_CLOUD_ALLOWED=1 -> 升级云端模型（先敏感信息过滤，dump 内容严禁外发）
  4. 在检出缺陷 commit 的分支上 git apply 生成补丁（--dry-run 只输出诊断）
  5. bot 推送 fix/defect-<ID> 分支并创建 MR（描述含诊断与指纹引用），Issue 评论 MR 链接
  6. 人工 review 合入；CI 回归通过后人工关闭 Issue（AI 不自动合入/关闭）

用法:
  python ai_fix.py --repo-dir /opt/bms/bms            # 扫描全部未关闭自动缺陷
  python ai_fix.py --repo-dir /opt/bms/bms --issue 42  # 处理单个 Issue
  python ai_fix.py --repo-dir /opt/bms/bms --dry-run   # 只出诊断与补丁，不提 MR

环境变量:
  GITLAB_API_URL / GITLAB_API_TOKEN / CI_PROJECT_ID   GitLab（同 defect_capture.py）
  GIT_PUSH_TOKEN      推送用令牌（git push 嵌入 URL；未设则要求本地已配置凭据）
  AI_CLOUD_ALLOWED    置 1 允许本地失败后升级云端（敏感信息过滤后仅发日志/代码）
  AI_CLOUD_URL / AI_CLOUD_KEY / AI_CLOUD_MODEL        云端 OpenAI 兼容端点（如可用服务）
  本地模型: LM_STUDIO_URL（默认 http://127.0.0.1:1234/v1）、LM_STUDIO_MODEL（缺省自动取）
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ARCHIVE_ROOT = "/mnt/data/backup/defects"
DEFAULT_LOCAL_URL = "http://127.0.0.1:1234/v1"
LABEL_AUTO = "defect-auto"
SECRET_PATTERN = ("password", "passwd", "secret", "token", "key", "PRIVATE-TOKEN")


def api(path: str, method: str = "GET", body: dict | None = None) -> dict | list | None:
    url = f"{os.environ['GITLAB_API_URL'].rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"PRIVATE-TOKEN": os.environ["GITLAB_API_TOKEN"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        print(f"[失败] GitLab API {method} {path} -> HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        sys.exit(1)


def chat(url: str, model: str, messages: list[dict], temperature: float = 0.2) -> str:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions",
        data=json.dumps({"model": model, "messages": messages,
                         "temperature": temperature}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        print(f"[失败] 模型 {url} -> HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        return ""
    except (urllib.error.URLError, KeyError, TimeoutError) as e:
        print(f"[失败] 模型 {url} 不可用: {e}")
        return ""


def sanitize_cloud(text: str) -> str:
    out = []
    for line in text.splitlines():
        if any(k in line.lower() for k in SECRET_PATTERN):
            out.append("<敏感行已掩码>")
        elif re.search(r"\.(sql|dmp|dump)\b", line) or "dump" in line.lower():
            out.append(re.sub(r"/mnt/data/backup/defects/\S+", "<dump 路径（含业务数据，禁止外发）>", line))
        else:
            out.append(line)
    return "\n".join(out)


def find_repro_dir(description: str) -> Path:
    m = re.search(r"/mnt/data/backup/defects/([A-Za-z0-9._-]+)", description)
    if not m:
        return Path()
    return Path(DEFAULT_ARCHIVE_ROOT) / m.group(1)


def gather_context(issue: dict, repo: Path) -> str:
    parts = [f"## Issue 标题\n{issue['title']}", f"## Issue 描述\n{issue['description']}"]
    repro = find_repro_dir(issue["description"])
    if repro.is_dir():
        for name in ("repro.json", "REPRO.md", "stacktrace.txt"):
            f = repro / name
            if f.is_file():
                parts.append(f"## {name}\n{f.read_text(encoding='utf-8', errors='replace')[:20000]}")
    else:
        parts.append("## 复现包\n（未在描述中找到归档路径）")
    test_file = ""
    meta = repro / "repro.json"
    if meta.is_file():
        try:
            test_file = json.loads(meta.read_text(encoding="utf-8")).get("test_file", "")
        except json.JSONDecodeError:
            pass
    if test_file:
        tf = repo / test_file
        if tf.is_file():
            parts.append(f"## 失败测试文件 {test_file}\n{tf.read_text(encoding='utf-8', errors='replace')[:20000]}")
    return "\n\n".join(parts)


PROMPT_SYS = (
    "你是 BMS 项目的缺陷修复代理。根据提供的缺陷上下文（Issue、复现包、失败测试文件），"
    "定位根因并给出修复。只输出 JSON："
    '{"diagnosis": "根因分析(中文)", "confidence": 0~1, '
    '"patch": "unified diff（git diff 格式，仅包含必要改动，不要包含测试改动；无法确定时为空串）"}'
)


def parse_patch(reply: str) -> dict:
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        return {"diagnosis": reply[:500], "confidence": 0.0, "patch": ""}
    try:
        data = json.loads(m.group(0))
        return {"diagnosis": str(data.get("diagnosis", "")), "confidence": float(data.get("confidence", 0.0)),
                "patch": str(data.get("patch", ""))}
    except (json.JSONDecodeError, ValueError):
        return {"diagnosis": reply[:500], "confidence": 0.0, "patch": ""}


def run(cmd: list[str], cwd: Path) -> bool:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd).returncode == 0


def create_mr(project_id: str, source: str, issue_iid: int, title: str, description: str) -> str:
    mr = api(f"projects/{project_id}/merge_requests", "POST", {
        "source_branch": source, "target_branch": "main",
        "title": title, "description": description})
    return mr["web_url"]


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 缺陷修复代理（双轨：本地→云端，AI 提 MR 人工合入）")
    parser.add_argument("--repo-dir", default=".", help="仓库目录")
    parser.add_argument("--issue", type=int, default=0, help="指定 Issue IID（缺省扫描全部未关闭自动缺陷）")
    parser.add_argument("--dry-run", action="store_true", help="只输出诊断与补丁，不提交不提 MR")
    args = parser.parse_args()

    repo = Path(args.repo_dir)
    if not (repo / ".git").is_dir():
        print(f"[失败] 不是 git 仓库: {repo}")
        return 2
    for key in ("GITLAB_API_URL", "GITLAB_API_TOKEN", "CI_PROJECT_ID"):
        if key not in os.environ:
            print(f"[失败] 缺少环境变量 {key}")
            return 2

    project_id = os.environ["CI_PROJECT_ID"]
    label_q = urllib.parse.quote(LABEL_AUTO)
    if args.issue:
        issues = [api(f"projects/{project_id}/issues/{args.issue}")]
    else:
        issues = api(f"projects/{project_id}/issues?scope=all&state=opened&labels={label_q}")
        issues = [i for i in issues or [] if "已提 MR" not in i.get("description", "")]
    if not issues:
        print("[完成] 无待处理的自动缺陷 Issue")
        return 0

    local_url = os.environ.get("LM_STUDIO_URL", DEFAULT_LOCAL_URL)
    local_model = os.environ.get("LM_STUDIO_MODEL", "")
    if not local_model:
        try:
            with urllib.request.urlopen(f"{local_url}/models", timeout=5) as resp:
                models = json.loads(resp.read()).get("data", [])
                if models:
                    local_model = models[0]["id"]
        except Exception:
            pass
    cloud_allowed = os.environ.get("AI_CLOUD_ALLOWED") == "1"

    for issue in issues:
        iid = issue["iid"]
        print(f"\n=== 处理 Issue !{iid} {issue['title']} ===")
        context = gather_context(issue, repo)
        messages = [{"role": "system", "content": PROMPT_SYS},
                    {"role": "user", "content": context}]

        reply = chat(local_url, local_model, messages) if local_model else ""
        result = parse_patch(reply)
        used_cloud = False
        if (not result["patch"] or result["confidence"] < 0.6) and cloud_allowed:
            print("[升级] 本地模型未能给出可靠修复，升级云端（敏感信息过滤后）")
            messages[1] = {"role": "user", "content": sanitize_cloud(context)}
            reply = chat(os.environ["AI_CLOUD_URL"], os.environ["AI_CLOUD_MODEL"], messages)
            result = parse_patch(reply)
            used_cloud = True
        print(f"[诊断] {result['diagnosis']}（置信度 {result['confidence']}，"
              f"模型：{'云端' if used_cloud else '本地'}）")

        if not result["patch"]:
            body = f"AI 未能自动定位修复：{result['diagnosis'][:500]}（需人工处理）"
            api(f"projects/{project_id}/issues/{iid}/notes", "POST", {"body": body})
            print(f"[完成] 已评论 Issue !{iid} 需人工处理")
            continue

        defect_id = find_repro_dir(issue["description"]).name or f"issue{iid}"
        branch = f"fix/defect-{defect_id}"
        if not run(["git", "-C", str(repo), "checkout", "-B", branch], repo):
            continue
        patch_path = repo / ".defect.patch"
        patch_path.write_text(result["patch"], encoding="utf-8")
        if not run(["git", "-C", str(repo), "apply", "--check", str(patch_path)], repo):
            print(f"[失败] 补丁不适用于当前代码（{result['patch'][:200]}）")
            continue
        run(["git", "-C", str(repo), "apply", str(patch_path)], repo)
        run(["git", "-C", str(repo), "add", "-A"], repo)
        if not run(["git", "-C", str(repo), "commit", "-m",
                    f"fix: AI 修复缺陷 !{iid}（{issue['title'][:60]}）"], repo):
            print("[跳过] 无改动可提交")
            continue
        if args.dry_run:
            print(f"[DRY-RUN] 已生成补丁，未推送：{patch_path}")
            continue

        push_token = os.environ.get("GIT_PUSH_TOKEN")
        project_path = os.environ.get("CI_PROJECT_PATH", "")
        if push_token and project_path:
            host = os.environ["GITLAB_API_URL"].split("/api")[0].split("//")[1]
            run(["git", "-C", str(repo), "push", "-u",
                 f"http://oauth2:{push_token}@{host}/{project_path}.git", branch], repo)
        else:
            run(["git", "-C", str(repo), "push", "-u", "origin", branch], repo)

        mr_url = create_mr(project_id, branch, iid,
                           f"fix: 自动缺陷 !{iid} {issue['title'][:40]}",
                           f"AI 修复（{result['diagnosis'][:300]}）\n\n"
                           f"指纹：见 Issue !{iid}\n请人工 review 后合入；CI 回归通过后可关闭 Issue。")
        api(f"projects/{project_id}/issues/{iid}/notes", "POST",
            {"body": f"AI 已提交修复 MR: {mr_url}（置信度 {result['confidence']}）"})
        print(f"[完成] MR: {mr_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
