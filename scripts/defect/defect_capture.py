"""缺陷现场自动归档与上报（CI 失败时调用，也可手动用于人工/UAT 缺陷）。

功能:
  1. 导出问题现场数据库 dump 到归档目录（默认 /mnt/data/backup/defects/<缺陷ID>/，
     环境变量 DEFECT_ARCHIVE_DIR 可覆盖；目录不随仓库入库，含业务数据）
  2. 生成 REPRO 复现包（供 AI 自动辨识与修复，见《测试规范》9 节）:
     - stacktrace.txt  全量失败堆栈/日志（从 --log-dir 收集或直接传入）
     - repro.json      结构化上下文（commit、用例 ID、测试文件与命令、dump 路径、环境）
     - REPRO.md        AI 可读的复现与修复指引
  3. 按 用例ID+失败摘要 生成缺陷指纹，查 GitLab 未关闭的同指纹 Issue：
     - 不存在 -> 自动创建 Issue（标题/描述含 commit、用例 ID、dump 路径、环境标记）
     - 已存在 -> 追加评论（附新 dump 路径与 commit）
  4. 输出 Issue URL 与归档路径（供 CI 日志与后续人工处理）

用法:
  python defect_capture.py --engine mysql --db-name bms_test_1 \
      --db-host 127.0.0.1 --db-port 3306 --db-user root --db-password x \
      --case-id 1234 --summary "test_create_user_returns_500" \
      --test-file tests/test_user_api.py --test-command "uv run pytest tests/test_user_api.py -k 1234" \
      --log-dir report
  python defect_capture.py --engine dm8 --db-name bms_dev \
      --case-id 5678 --summary "三库方言分页失败"     # 在 mjbk 主机执行（本地 dexp）

环境变量（GitLab CI 预置或 CI/CD 变量）:
  GITLAB_API_URL     GitLab API 地址，如 http://<mjbk-IP>/api/v4（不硬编码内网地址）
  GITLAB_API_TOKEN   API 令牌（bot 账号，api 权限；存 CI/CD 变量，勿入库）
  CI_PROJECT_ID      项目 ID（GitLab 预置变量，本地手动运行时需手动指定）
  CI_COMMIT_SHA      当前 commit（GitLab 预置变量）
  CI_PIPELINE_URL    流水线地址（GitLab 预置变量）
  DEFECT_ARCHIVE_DIR 归档根目录，默认 /mnt/data/backup/defects
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

DEFAULT_ARCHIVE_ROOT = "/mnt/data/backup/defects"

LABEL_AUTO = "defect-auto"


def load_env(path: Path) -> dict:
    env = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return env
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[失败] 命令执行失败: {' '.join(cmd)}\n{result.stderr.strip()}")
        sys.exit(1)
    return result


def dump_mysql(args) -> Path:
    out = args.out_dir / f"{args.db_name}-{date.today().isoformat()}.sql"
    # --ssl=0：内网自签证书环境（mariadb 客户端默认尝试 TLS 会握手失败）
    run(["mysqldump", "--single-transaction", "--ssl=0", "-h", args.db_host, "-P", str(args.db_port),
         "-u", args.db_user, f"-p{args.db_password}", args.db_name, "-r", str(out)])
    return out


def dump_postgres(args) -> Path:
    out = args.out_dir / f"{args.db_name}-{date.today().isoformat()}.dump"
    env = dict(os.environ, PGPASSWORD=args.db_password)
    subprocess.run(["pg_dump", "-h", args.db_host, "-p", str(args.db_port), "-U", args.db_user,
                    "-Fc", args.db_name, "-f", str(out)], env=env, check=True)
    return out


def dump_dm8(args) -> Path:
    out = args.out_dir / f"{args.db_name}-{date.today().isoformat()}.dmp"
    run(["/opt/dmdbms/bin/dexp", f"SYSDBA/{args.db_password}@{args.db_host}:{args.db_port}",
         f"FILE={out.name}", f"DIRECTORY={args.out_dir}", f"OWNER={args.db_name}", "LOG=exp.log"])
    return out


def fingerprint(case_id: str, summary: str) -> str:
    norm = " ".join(summary.split()).lower()
    return hashlib.sha256(f"{case_id}|{norm}".encode("utf-8")).hexdigest()[:12]


def collect_logs(log_dir: str | None, out_dir: Path) -> list[str]:
    if not log_dir:
        return []
    src = Path(log_dir)
    if not src.is_dir():
        print(f"[警告] 日志目录不存在: {src}")
        return []
    dst = out_dir / "logs"
    dst.mkdir(parents=True, exist_ok=True)
    names = []
    for f in sorted(src.iterdir()):
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            names.append(f.name)
    return names


def write_repro(args, fp: str, dump_path: Path) -> Path:
    stack = ""
    st = args.out_dir / "stacktrace.txt"
    if args.stacktrace:
        st.write_text(args.stacktrace, encoding="utf-8")
        stack = f"stacktrace.txt（{len(args.stacktrace)} 字符）"
    logs = [f"logs/{n}" for n in collect_logs(args.log_dir, args.out_dir)]
    meta = {
        "defect_id": args.defect_id,
        "fingerprint": fp,
        "commit": args.commit,
        "case_id": args.case_id,
        "engine": args.engine,
        "db_name": args.db_name,
        "dump_path": str(dump_path),
        "test_file": args.test_file,
        "test_command": args.test_command,
        "stacktrace": stack,
        "logs": logs,
        "env": args.env,
        "pipeline_url": args.pipeline_url,
    }
    (args.out_dir / "repro.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    md = args.out_dir / "REPRO.md"
    md.write_text(
        f"# 缺陷复现包 {args.defect_id}\n\n"
        f"- 指纹：`{fp}`\n"
        f"- 用例 ID：{args.case_id or '未关联'}\n"
        f"- 代码 commit：`{args.commit}`\n"
        f"- 测试库：{args.engine} / {args.db_name}\n"
        f"- 测试文件：{args.test_file or '未知'}\n"
        f"- 复现命令：`{args.test_command or '未知'}`\n"
        f"- 现场 dump：`{dump_path}`（含业务数据，仅限内网处理）\n"
        f"- 失败堆栈：{stack or '未收集'}\n"
        f"- 相关日志：{', '.join(logs) if logs else '未收集'}\n"
        f"- 环境标记：{args.env}\n"
        f"- 流水线：{args.pipeline_url or '本地运行'}\n\n"
        f"## 复现步骤\n\n"
        f"1. `git checkout {args.commit}`\n"
        f"2. 导入 dump（`scripts/defect/reproduce.py --dump {dump_path}` 或手动恢复）\n"
        f"3. 执行：{args.test_command or '按测试文件对应用例执行'}\n\n"
        f"## 修复指引（AI 代理）\n\n"
        f"- 先读 repro.json 与 stacktrace.txt，定位失败断言与堆栈位置\n"
        f"- 修复后按上述命令回归验证，CI 绿后提 MR 引用本缺陷指纹\n",
        encoding="utf-8")
    return md


def build_description(args, fp: str, dump_path: Path, repro_md: Path) -> str:
    return (
        f"**自动缺陷上报**（指纹 `{fp}`）\n\n"
        f"- 缺陷指纹：`{fp}`\n"
        f"- 用例 ID：{args.case_id or '未关联'}\n"
        f"- 代码 commit：`{args.commit or '未知'}`\n"
        f"- 测试库：{args.engine} / {args.db_name}\n"
        f"- 测试文件：{args.test_file or '未知'}\n"
        f"- 现场 dump：`{dump_path}`（mjbk 本机归档，随每日备份保留 30 天，不入 Git）\n"
        f"- 复现包：`{repro_md}`（REPRO.md / repro.json / stacktrace.txt，AI 修复代理输入）\n"
        f"- 环境标记：{args.env or '见流水线'}\n"
        f"- 失败摘要：{args.summary}\n"
        f"- 流水线：{args.pipeline_url or '本地运行'}\n\n"
        f"处理方式：按《测试规范》9 节，AI 修复代理按复现包定位修复并提 MR（人工 review 合入），"
        f"验证按「代码 commit + 用例 + dump 导入」重建现场。"
    )


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


def find_open_issue(project_id: str, fp: str) -> dict | None:
    q = urllib.parse.quote(fp)
    issues = api(f"projects/{project_id}/issues?scope=all&state=opened&search={q}")
    for issue in issues or []:
        if fp in f"{issue.get('title', '')} {issue.get('description', '')}":
            return issue
    return None


def main() -> int:
    env = load_env(Path(__file__).resolve().parents[2] / "deploy" / ".env")
    parser = argparse.ArgumentParser(description="缺陷现场自动归档与上报")
    parser.add_argument("--engine", required=True, choices=["mysql", "postgres", "dm8"])
    parser.add_argument("--db-name", required=True, help="测试库名（mysql 为库，dm8 为模式名）")
    parser.add_argument("--db-host", default=env.get("MJBK_IP", ""), help="数据库主机（默认取 deploy/.env 的 MJBK_IP）")
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", default="root")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--case-id", default="", help="Kiwi TCMS 用例 ID")
    parser.add_argument("--summary", required=True, help="失败摘要（用于标题与指纹）")
    parser.add_argument("--env", default="CI", help="环境标记")
    parser.add_argument("--defect-id", default="", help="缺陷号（缺省自动生成 commit 短号）")
    parser.add_argument("--test-file", default="", help="失败测试文件路径（写入 REPRO 包）")
    parser.add_argument("--test-command", default="", help="复现测试命令（写入 REPRO 包）")
    parser.add_argument("--stacktrace", default="", help="失败堆栈全文（未提供时尝试从 --log-dir 提取）")
    parser.add_argument("--log-dir", default="", help="失败日志目录（复制进归档 logs/）")
    args = parser.parse_args()

    commit = os.environ.get("CI_COMMIT_SHA", args.defect_id or "local")
    defect_id = args.defect_id or commit[:12]
    args.defect_id = defect_id
    archive_root = Path(os.environ.get("DEFECT_ARCHIVE_DIR", DEFAULT_ARCHIVE_ROOT))
    args.out_dir = archive_root / defect_id
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.commit = commit
    args.pipeline_url = os.environ.get("CI_PIPELINE_URL", "")

    print(f"[1/3] 导出 {args.engine} 现场数据 -> {args.out_dir}")
    dump = {"mysql": dump_mysql, "postgres": dump_postgres, "dm8": dump_dm8}[args.engine](args)
    print(f"[完成] 现场 dump: {dump}")

    fp = fingerprint(args.case_id or "n/a", args.summary)
    repro_md = write_repro(args, fp, dump)
    print(f"[完成] REPRO 复现包: {repro_md}")

    if not (os.environ.get("GITLAB_API_URL") and os.environ.get("GITLAB_API_TOKEN")):
        print("[跳过] 未配置 GITLAB_API_URL / GITLAB_API_TOKEN，仅归档复现包；请人工建 Issue 并引用上述路径。")
        return 0

    project_id = os.environ.get("CI_PROJECT_ID", "")
    if not project_id:
        print("[跳过] 未配置 CI_PROJECT_ID，仅归档复现包。")
        return 0

    print(f"[2/3] 查询同指纹未关闭 Issue（指纹 {fp}）")
    issue = find_open_issue(project_id, fp)
    if issue:
        note = f"再次失败（commit `{commit}`）：新现场 dump `{dump}`，复现包 `{repro_md}`，见流水线 {args.pipeline_url}"
        api(f"projects/{project_id}/issues/{issue['iid']}/notes", "POST", {"body": note})
        url = issue["web_url"]
        print(f"[3/3] 已追加评论到现有 Issue: {url}")
    else:
        issue = api(f"projects/{project_id}/issues", "POST", {
            "title": f"[自动缺陷] {args.summary}",
            "description": build_description(args, fp, dump, repro_md),
            "labels": LABEL_AUTO,
        })
        url = issue["web_url"]
        print(f"[3/3] 已创建自动缺陷 Issue: {url}")

    print(f"归档目录: {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
