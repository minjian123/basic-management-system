"""缺陷一键复现（REPRO 包配套，供人工与 AI 修复代理使用）。

功能:
  1. 检出缺陷对应 commit（--repo-dir 仓库，缺省 -C 检出）
  2. 导入现场 dump 到指定库（mysql 用 mysql client，postgres 用 pg_restore/psql，
     达梦用 disql 执行，需在 mjbk 主机运行）
  3. 执行复现命令（--test-command 或 REPRO.md 中登记的测试命令）
  4. 输出复现结果与退出码

用法:
  python reproduce.py --issue-repro /mnt/data/backup/defects/abc123 \
      --repo-dir /opt/bms/bms --dump-target bms_repro
  python reproduce.py --commit <hash> --test-command "uv run pytest tests/test_user_api.py -k 1234" \
      --dump /mnt/data/backup/defects/abc123/bms_test_1.sql --engine mysql \
      --db-host 127.0.0.1 --db-user root --db-password x --dump-target bms_repro

环境变量:
  MYSQL_CLIENT / PG_CLIENT / DM_DISQL   客户端路径（缺省自动探测常见路径）
  DEFECT_ARCHIVE_DIR                     复现包根目录，默认 /mnt/data/backup/defects
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ARCHIVE_ROOT = "/mnt/data/backup/defects"


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd)


def load_repro(issue_repro: str) -> dict:
    root = Path(issue_repro)
    meta_file = root / "repro.json"
    if not meta_file.is_file():
        print(f"[失败] 未找到 {meta_file}（该目录不是完整复现包）")
        sys.exit(2)
    return json.loads(meta_file.read_text(encoding="utf-8"))


def import_dump(args) -> None:
    if args.engine == "mysql":
        run([args.mysql_client, "-h", args.db_host, "-P", str(args.db_port),
             "-u", args.db_user, f"-p{args.db_password}", args.dump_target,
             "-e", f"SOURCE {args.dump}"])
    elif args.engine == "postgres":
        run([args.pg_client, "-h", args.db_host, "-p", str(args.db_port),
             "-U", args.db_user, "-d", args.dump_target, "-f", str(args.dump)])
    elif args.engine == "dm8":
        run(["/opt/dmdbms/bin/dimp", f"SYSDBA/{args.db_password}@{args.db_host}:{args.db_port}",
             f"FILE={args.dump}", f"OWNER={args.dump_target}"])
    else:
        print(f"[失败] 不支持的引擎: {args.engine}")
        sys.exit(2)


def main() -> int:
    env = load_env(Path(__file__).resolve().parents[2] / "deploy" / ".env")
    parser = argparse.ArgumentParser(description="缺陷一键复现")
    parser.add_argument("--issue-repro", default="", help="复现包目录（读 repro.json）")
    parser.add_argument("--repo-dir", default=".", help="仓库目录（缺省当前目录）")
    parser.add_argument("--commit", default="", help="检出 commit（缺省读 repro.json）")
    parser.add_argument("--test-command", default="", help="复现测试命令（缺省读 repro.json）")
    parser.add_argument("--dump", default="", help="dump 文件路径（缺省读 repro.json）")
    parser.add_argument("--engine", choices=["mysql", "postgres", "dm8"], default="")
    parser.add_argument("--db-host", default=env.get("MJBK_IP", ""))
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", default="root")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--dump-target", required=True, help="导入目标库名（需先建库）")
    parser.add_argument("--mysql-client", default="mysql")
    parser.add_argument("--pg-client", default="psql")
    parser.add_argument("--dm-disql", default="/opt/dmdbms/bin/disql")
    args = parser.parse_args()

    meta = load_repro(args.issue_repro) if args.issue_repro else {}
    commit = args.commit or meta.get("commit", "")
    test_cmd = args.test_command or meta.get("test_command", "")
    dump = args.dump or meta.get("dump_path", "")
    engine = args.engine or meta.get("engine", "")
    if not dump or not engine or not test_cmd:
        print("[失败] 需要 dump/engine/复现命令（--issue-repro 或显式参数，见 REPRO.md）")
        return 2

    repo = Path(args.repo_dir)
    if not (repo / ".git").is_dir():
        print(f"[失败] 不是 git 仓库: {repo}")
        return 2

    print(f"[1/3] 检出 commit {commit}")
    if run(["git", "-C", str(repo), "checkout", commit]).returncode != 0:
        return 1

    print(f"[2/3] 导入 dump {dump} -> {args.dump_target}（{engine}）")
    import_dump(args)

    print(f"[3/3] 执行复现命令: {test_cmd}")
    return run(test_cmd.split(), cwd=str(repo)).returncode


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


if __name__ == "__main__":
    sys.exit(main())
