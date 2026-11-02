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
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# GitLab JSON / 命令行参数是动态结构（`json.loads` 结果无法静态表达），与 scripts/tools/ci/status.py 同口径：
# 只放宽「未知类型」三条，其余检查照常。
from pathlib import Path
from typing import Any

DEFAULT_ARCHIVE_ROOT = "/mnt/data/backup/defects"

LABEL_AUTO = "defect-auto"

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402


def load_env(path: Path) -> ConcurrentStableDict[str, str]:
    env: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return env
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env.set(key.strip(), value.strip().strip('"').strip("'"))
    return env


def run(cmd: ConcurrentStableList[str]) -> subprocess.CompletedProcess[str] | None:
    """执行命令；失败或工具缺失返回 `None`（现场捕获尽力而为，不阻断归档）。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"[跳过] 工具不可用: {cmd[0]}")
        return None
    if result.returncode != 0:
        print(f"[跳过] 命令执行失败: {' '.join(cmd)}\n{result.stderr.strip()}")
        return None
    return result


def dump_mysql(args: Any) -> Path | None:
    out = args.out_dir / f"{args.db_name}-{date.today().isoformat()}.sql"
    # --ssl=0：内网自签证书环境（mariadb 客户端默认尝试 TLS 会握手失败）
    result = run(
        ConcurrentStableList(
            [
                "mysqldump",
                "--single-transaction",
                "--ssl=0",
                "-h",
                args.db_host,
                "-P",
                str(args.db_port),
                "-u",
                args.db_user,
                f"-p{args.db_password}",
                args.db_name,
                "-r",
                str(out),
            ]
        )
    )
    return out if result is not None else None


def dump_postgres(args: Any) -> Path | None:
    out = args.out_dir / f"{args.db_name}-{date.today().isoformat()}.dump"
    env = dict(os.environ, PGPASSWORD=args.db_password)
    try:
        subprocess.run(
            [
                "pg_dump",
                "-h",
                args.db_host,
                "-p",
                str(args.db_port),
                "-U",
                args.db_user,
                "-Fc",
                args.db_name,
                "-f",
                str(out),
            ],
            env=env,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        print(f"[跳过] pg_dump 不可用: {error}")
        return None
    return out


def dump_dm8(args: Any) -> Path | None:
    out = args.out_dir / f"{args.db_name}-{date.today().isoformat()}.dmp"
    result = run(
        ConcurrentStableList(
            [
                "/opt/dmdbms/bin/dexp",
                f"SYSDBA/{args.db_password}@{args.db_host}:{args.db_port}",
                f"FILE={out.name}",
                f"DIRECTORY={args.out_dir}",
                f"OWNER={args.db_name}",
                "LOG=exp.log",
            ]
        )
    )
    return out if result is not None else None


_VOLATILE = re.compile(
    r"https?://\S+"  # 流水线 / 作业地址
    r"|@\s*[0-9a-f]{7,40}"  # commit 短号 / 全号
    r"|0x[0-9a-f]{6,}"  # 内存地址
    r"|\b\d{4,}\b"  # 长数字（ID / 计数 / sha 片段）
)
"""指纹归一化时剥掉的易变片段。

留着这些会让「同一根因」每次流水线都算出新指纹——实测积压 113 张单对应 113 个指纹，
全部无法聚类，也就无法判断「这张是不是已经修过」。
"""

_FAILED_CASE = re.compile(r"FAILED\s+(\S+?::\S+)")
"""pytest 失败清单行里的 `文件::用例`。"""

_EXC_LINE = re.compile(r"((?:[A-Za-z_][\w.]*\.)?[A-Za-z_]\w*(?:Error|Exception|Failure))(?::\s*(.*))?")
"""异常类型行（`ModuleNotFoundError: ...` / `AssertionError` / `sqlalchemy.exc.XxxError`）。"""


def fingerprint(case_id: str, summary: str) -> str:
    """计算缺陷指纹（同根因同指纹，供去重）。

    归一化剥掉 commit / URL / 长数字后取 sha256 前 12 位。摘要里带「失败 job | 用例 | 异常类型」
    时聚类最准；只有流水线级描述时也能把「同一 job 的同一异常」归到一起。

    Args:
        case_id: 用例 ID（无则传 `n/a`）。
        summary: 失败摘要。

    Returns:
        str: 12 位十六进制指纹。
    """
    norm = " ".join(summary.split()).lower()
    norm = _VOLATILE.sub("<x>", norm)
    return hashlib.sha256(f"{case_id}|{norm}".encode()).hexdigest()[:12]


def _api_json(path: str, *, raw: bool = False) -> Any:
    """GET GitLab 接口（CI 内运行：用 CI_API_V4_URL + GITLAB_API_TOKEN）。

    Args:
        path: 相对 API 根路径。
        raw: True 返回原文（job trace 是纯文本）。

    Returns:
        Any: 解析后的 JSON / 文本；无内容返回 None / 空串。
    """
    base = (os.environ.get("CI_API_V4_URL") or os.environ.get("GITLAB_API_URL", "")).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    req = urllib.request.Request(
        url,
        headers={"PRIVATE-TOKEN": os.environ.get("GITLAB_API_TOKEN", "")},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    if raw:
        return payload.decode("utf-8", errors="replace")
    return json.loads(payload) if payload else None


_PRIMARY_HINTS = (
    "[contract_gate]",
    "破坏性变更",
    "未达标",
    "FAILED ",
    "AssertionError",
    "Traceback (most recent call last)",
)
"""失败日志里优先提取的结论行关键字（先命中先返回）。"""

_LOG_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+\S+\s+")
"""日志行前缀（ISO 时间戳 + 01O 之类的流标记）：同一条结论每次前缀都不同，进指纹前须剥掉。"""

_NOISE_HINTS = ("instrumentation_skipped", "warning  ]", "WARNING ", "Job failed: exit code")
"""已知噪音（初始化告警 / 收尾行），不得冒充失败原因。"""


def _digest(lines: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """从日志尾部提取「失败结论行」。

    先按 `_PRIMARY_HINTS` 找门禁结论 / pytest 失败清单 / 异常栈头；都没命中时兜底抓异常行，
    但**跳过噪音**——否则会把 `instrumentation_skipped` 这类初始化告警当成根因。

    Args:
        lines: 日志行（尾部片段）。

    Returns:
        ConcurrentStableList[str]: 结论行（最多 3 行）。
    """
    for hint in _PRIMARY_HINTS:
        hits = ConcurrentStableList(ln for ln in lines if hint in ln)
        if hits:
            return ConcurrentStableList(_LOG_PREFIX.sub("", ln).strip() for ln in list(hits)[-3:])
    fallback = ConcurrentStableList(
        ln for ln in lines if not any(noise in ln for noise in _NOISE_HINTS) and ("Error" in ln or "Exception" in ln)
    )
    return ConcurrentStableList(_LOG_PREFIX.sub("", ln).strip() for ln in list(fallback)[-3:])


def collect_pipeline_failures() -> ConcurrentStableDict[str, str]:
    """从当前流水线提取失败 job、首个失败用例与异常类型。

    为什么需要：原上报只写 `main pipeline failure @ <sha> (<url>)`——含 sha 导致指纹每次都变，
    且没有 job / 用例信息，缺陷单既无法聚类也无法定位（「测试文件：未知」即由此而来）。

    Returns:
        ConcurrentStableDict[str, str]: `summary` / `stacktrace` / `test_file`；取不到时各为空串。
    """
    out: ConcurrentStableDict[str, str] = ConcurrentStableDict({"summary": "", "stacktrace": "", "test_file": ""})
    project = os.environ.get("CI_PROJECT_ID", "")
    pipeline = os.environ.get("CI_PIPELINE_ID", "")
    if not (project and pipeline and (os.environ.get("CI_API_V4_URL") or os.environ.get("GITLAB_API_URL"))):
        return out
    try:
        jobs = _api_json(f"projects/{project}/pipelines/{pipeline}/jobs?per_page=100")
    except urllib.error.URLError, ValueError:
        return out
    if not isinstance(jobs, list):
        return out

    failed = [job for job in jobs if job.get("status") == "failed" and job.get("allow_failure") is not True]
    if not failed:
        return out

    names: ConcurrentStableList[str] = ConcurrentStableList()
    details: ConcurrentStableList[str] = ConcurrentStableList()
    cases: ConcurrentStableList[str] = ConcurrentStableList()
    first_exc = ""
    for job in failed:
        name = str(job.get("name", ""))
        names.add(name)
        try:
            trace = str(_api_json(f"projects/{project}/jobs/{job.get('id')}/trace", raw=True))
        except urllib.error.URLError, ValueError:
            continue
        tail = trace.splitlines()[-400:]
        for line in tail:
            matched = _FAILED_CASE.search(line)
            if matched and matched.group(1) not in cases:
                cases.add(matched.group(1))
            if not first_exc:
                digest = _digest(ConcurrentStableList(tail))
                if digest:
                    first_exc = str(digest[0]).strip()[:160]
        details.add(
            f"\n### {name}\n```\n"
            + "\n".join([ln for ln in tail if _FAILED_CASE.search(ln) or "Error" in ln][-6:])
            + "\n```"
        )

    if not names:
        return out
    out.set("summary", f"pipeline failure: {','.join(names)} | {(cases[0] if cases else '-')} | {first_exc or '-'}")
    out.set("stacktrace", "\n".join(details))
    if cases:
        out.set("test_file", cases[0].split("::")[0])
    return out


def collect_logs(log_dir: str | None, out_dir: Path) -> ConcurrentStableList[str]:
    if not log_dir:
        return ConcurrentStableList()
    src = Path(log_dir)
    if not src.is_dir():
        print(f"[警告] 日志目录不存在: {src}")
        return ConcurrentStableList()
    dst = out_dir / "logs"
    dst.mkdir(parents=True, exist_ok=True)
    names: ConcurrentStableList[str] = ConcurrentStableList()
    for f in sorted(src.iterdir()):
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            names.add(f.name)
    return names


def write_repro(args: Any, fp: str, dump_path: Path | None) -> Path:
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
        "dump_path": str(dump_path) if dump_path else "",
        "test_file": args.test_file,
        "test_command": args.test_command,
        "stacktrace": stack,
        "logs": logs,
        "env": args.env,
        "pipeline_url": args.pipeline_url,
    }
    (args.out_dir / "repro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

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
        f"2. 导入 dump（`scripts/tools/defect/reproduce.py --dump {dump_path}` 或手动恢复）\n"
        f"3. 执行：{args.test_command or '按测试文件对应用例执行'}\n\n"
        f"## 修复指引（AI 代理）\n\n"
        f"- 先读 repro.json 与 stacktrace.txt，定位失败断言与堆栈位置\n"
        f"- 修复后按上述命令回归验证，CI 绿后提 MR 引用本缺陷指纹\n",
        encoding="utf-8",
    )
    return md


def build_description(args: Any, fp: str, dump_path: Path | None, repro_md: Path) -> str:
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


def api(
    path: str,
    method: str = "GET",
    body: ConcurrentStableDict[str, object] | None = None,
) -> Any:
    url = f"{os.environ['GITLAB_API_URL'].rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(dict(body)).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"PRIVATE-TOKEN": os.environ["GITLAB_API_TOKEN"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
            if not payload:
                return None
            parsed: object = json.loads(payload)
            if isinstance(parsed, dict):
                return ConcurrentStableDict(parsed)
            if isinstance(parsed, list):
                return ConcurrentStableList(parsed)
            return None
    except urllib.error.HTTPError as e:
        print(f"[失败] GitLab API {method} {path} -> HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        sys.exit(1)


def find_open_issue(project_id: str, fp: str) -> ConcurrentStableDict[str, object] | None:
    q = urllib.parse.quote(fp)
    issues = api(f"projects/{project_id}/issues?scope=all&state=opened&search={q}")
    for issue in issues or []:
        if fp in f"{issue.get('title', '')} {issue.get('description', '')}":
            return ConcurrentStableDict(issue)
    return None


def main() -> int:
    env = load_env(Path(__file__).resolve().parents[3] / "deploy" / ".env")
    parser = argparse.ArgumentParser(description="缺陷现场自动归档与上报")
    parser.add_argument("--engine", required=True, choices=["mysql", "postgres", "dm8"])
    parser.add_argument("--db-name", required=True, help="测试库名（mysql 为库，dm8 为模式名）")
    parser.add_argument("--db-host", default=env.get("MJBK_IP", ""), help="数据库主机（默认取 deploy/.env 的 MJBK_IP）")
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", default="root")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--case-id", default="", help="Kiwi TCMS 用例 ID")
    parser.add_argument("--summary", default="", help="失败摘要（用于标题与指纹；留空则由采集开关自动生成）")
    parser.add_argument(
        "--collect-pipeline-failures",
        action="store_true",
        help="从当前流水线采集失败 job / 失败用例 / 异常类型，补全 summary 与 stacktrace（CI on_failure 用）",
    )
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
    if dump:
        print(f"[完成] 现场 dump: {dump}")
    else:
        print("[跳过] 现场数据 dump 不可用（库不存在 / 客户端缺失）；继续归档 REPRO 包")

    if args.collect_pipeline_failures:
        collected = collect_pipeline_failures()
        if collected.get("summary"):
            args.summary = collected["summary"]
            args.stacktrace = args.stacktrace or collected["stacktrace"]
            args.test_file = args.test_file or collected["test_file"]
            print(f"[采集] 失败摘要: {args.summary}")
        else:
            print("[采集] 未能从流水线取得失败 job（退回流水线级摘要）")
    if not args.summary:
        args.summary = f"main pipeline failure @ {commit[:8]}"

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
        api(f"projects/{project_id}/issues/{issue['iid']}/notes", "POST", ConcurrentStableDict({"body": note}))
        url = issue["web_url"]
        print(f"[3/3] 已追加评论到现有 Issue: {url}")
    else:
        issue = api(
            f"projects/{project_id}/issues",
            "POST",
            ConcurrentStableDict(
                {
                    "title": f"[自动缺陷] {args.summary}",
                    "description": build_description(args, fp, dump, repro_md),
                    "labels": LABEL_AUTO,
                }
            ),
        )
        url = issue["web_url"]
        print(f"[3/3] 已创建自动缺陷 Issue: {url}")

    print(f"归档目录: {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
