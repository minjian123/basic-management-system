#!/usr/bin/env python3
"""在 WSL 内一键复刻 bizs 开发环境（从只读挂载的双系统 Ubuntu 盘复制）。

背景与用法见 bms 文档《WSL 部署使用说明》「WSL 内开发环境」节。

设计口径（与双系统 Linux 侧保持一致是首要目标）：
  * 路径完全复刻：~/develop/bizs（工作区）+ ~/dev-deps（依赖仓）。
    原因：Linux 侧 .venv 内 38 个脚本的 shebang、pyvenv.cfg 的 home、
    node_modules 软链全是绝对路径 /home/minjian/...，路径一致才能直接复用依赖、零重装。
  * 代码从挂载分区 rsync 复制（不是 clone）：要拿到含 deploy/.env、database/*.db、
    跨仓软链的「正在跑的那一份」，而不是最新远端。
  * 依赖仓整目录复制后做导入自检；校验失败才回退到 pnpm install + uv sync。
  * 临时产物（tmp/、.playwright-mcp/、.playwright-cli/）不复制，目标端新建空目录。

安全：源端（挂载分区）全程只读，脚本不做任何写入。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402  (须先注入源码根)

# 挂载点形态固定（见《WSL 部署使用说明》3.5）；可用 --source 覆盖
DEFAULT_SOURCE = Path("/mnt/wsl/PHYSICALDRIVE3p2/home/minjian")
DEFAULT_MOUNT_POINT = Path("/mnt/wsl/PHYSICALDRIVE3p2")

# 不复制的工作区本地产物（历史临时文件 / 浏览器日志，与 WSL 环境无关）
# 模块级常量用固定元数 tuple（集合护栏口径：不落可变裸集合）
WORKSPACE_EXCLUDES = ("/tmp/", "/.playwright-mcp/", "/.playwright-cli/")

# 用户级配置文件（相对源 home）
USER_CONFIGS = (
    ".gitconfig",
    ".git-credentials",
    ".npmrc",
    ".config/uv/uv.toml",
    ".config/pip/pip.conf",
)

# 依赖仓子目录（bms 前端+后端、mdm 前端+后端）
DEPS_SUBDIRS = ("bms", "mdm")


def log(msg: str) -> None:
    print(f"[WSL开发环境] {msg}", flush=True)


def fail(msg: str) -> int:
    print(f"[WSL开发环境] 错误：{msg}", file=sys.stderr, flush=True)
    return 1


def run(
    cmd: list[str],  # bare-collections:allow subprocess argv 须内置 list
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture,
    )


def check_source(source: Path) -> str | None:
    """校验源端可用，返回错误信息或 None。"""
    if not DEFAULT_MOUNT_POINT.is_dir():
        return (
            f"未检测到挂载点 {DEFAULT_MOUNT_POINT}。\n"
            "请先在 Windows 侧挂载双系统 Ubuntu 盘（桌面快捷方式「挂载 Ubuntu 盘」，"
            "或 bms/scripts/tools/wsl/挂载Ubuntu盘.py）。"
        )
    if not (source / "develop/bizs").is_dir():
        return f"源端缺少工作区目录：{source / 'develop/bizs'}"
    if not (source / "dev-deps").is_dir():
        return f"源端缺少依赖仓目录：{source / 'dev-deps'}"
    return None


def check_prereqs() -> str | None:
    """校验 WSL 内前置条件。"""
    for tool in ("rsync", "git"):
        if shutil.which(tool) is None:
            return f"缺少命令 {tool}，请先安装：sudo apt-get install -y {tool}"
    if os.geteuid() == 0:
        return "请以普通用户运行（不要用 sudo）：脚本按当前用户 $HOME 落盘。"
    return None


def sync_tree(
    src: Path,
    dst: Path,
    excludes: list[str] | None = None,  # bare-collections:allow rsync argv 片段
) -> None:
    """rsync 复制目录树（保留硬链接以节省空间，不保留属主）。"""
    dst.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync",
        "-aH",
        "--no-owner",
        "--no-group",
        "--info=progress2",
    ]  # bare-collections:allow rsync argv
    for pattern in excludes or []:
        cmd += ["--exclude", pattern]
    cmd += [f"{src}/", f"{dst}/"]
    log(f"复制 {src} -> {dst}")
    run(cmd)


def copy_user_configs(source: Path) -> ConcurrentStableList[str]:
    """复制用户级配置，返回实际复制的清单。"""
    home = Path.home()
    copied: ConcurrentStableList[str] = ConcurrentStableList()
    for rel in USER_CONFIGS:
        src = source / rel
        if not src.exists():
            continue
        dst = home / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    return copied


def ensure_python_shim() -> bool:
    """venv 的 bin/python 指向 /usr/local/bin/python，WSL 默认没有该软链，需补建。

    返回 True 表示本次创建了软链（需要 root 权限）。
    """
    shim = Path("/usr/local/bin/python")
    if shim.exists() or shim.is_symlink():
        return False
    try:
        shim.symlink_to("/usr/bin/python3")
        return True
    except PermissionError:
        return False


def verify_backend(workspace: Path) -> tuple[bool, str]:
    """后端导入自检：工作区成员 + 关键第三方库 + 原生扩展。"""
    python = workspace / "bms/backend/.venv/bin/python"
    if not python.exists():
        return False, f"venv python 不存在：{python}"

    members = (
        "bms_core",
        "bms_txn",
        "bms_platform",
        "bms_identity",
        "bms_tenant",
        "bms_file",
        "bms_notification",
        "bms_search",
        "bms_ai",
        "bms_report",
    )
    script = (
        "import importlib, sys\n"
        f"mods = {members!r}\n"
        "bad = []\n"
        "for m in mods:\n"
        "    try: importlib.import_module(m)\n"
        "    except Exception as e: bad.append(f'{m}: {e}')\n"
        "for m in ['fastapi','sqlalchemy','pydantic','alembic','pytest','httpx','redis','fakeredis','minio','yaml']:\n"
        "    try: importlib.import_module(m)\n"
        "    except Exception as e: bad.append(f'{m}: {e}')\n"
        "for m in ['pydantic_core','coverage','lupa']:\n"
        "    try: importlib.import_module(m)\n"
        "    except Exception as e: bad.append(f'{m}: {e}')\n"
        "print('FAIL' if bad else 'OK')\n"
        "for b in bad: print(b)\n"
    )
    proc = run((str(python), "-c", script), check=False, capture=True)
    if proc.stdout.startswith("OK"):
        return True, "后端导入自检通过（10 工作区成员 + 10 第三方库 + 3 原生扩展）"
    return False, f"后端导入自检失败：\n{proc.stdout}{proc.stderr}"


def verify_frontend(workspace: Path) -> tuple[bool, str]:
    """前端自检：node_modules 软链可解析。"""
    pnpm = shutil.which("pnpm")
    node = shutil.which("node")
    if not node:
        return False, "未找到 node（请先装 nvm + node v24.20.0）"
    if not pnpm:
        return False, "未找到 pnpm（请先 npm i -g pnpm@11.7.0）"
    target = workspace / "bms/frontend/apps/desktop"
    proc = run(
        (node, "-e", f"require.resolve('vue', {{paths:['{target}']}})"),
        check=False,
        capture=True,
    )
    if proc.returncode == 0:
        return True, "前端 node_modules 可解析（vue）"
    return False, f"前端依赖解析失败：{proc.stderr.strip()}"


def report_versions() -> None:
    """打印关键工具版本，便于与双系统 Linux 侧比对。"""
    checks = (
        ("node", ("node", "--version")),
        ("pnpm", ("pnpm", "--version")),
        ("uv", ("uv", "--version")),
        ("python3", ("python3", "--version")),
    )
    for name, cmd in checks:
        exe = shutil.which(cmd[0])
        if not exe:
            print(f"  {name:<10} （未安装）")
            continue
        proc = run((exe, *cmd[1:]), check=False, capture=True)
        out = (proc.stdout or proc.stderr).strip().splitlines()
        print(f"  {name:<10} {out[0] if out else ''}")


def sync_repos(workspace: Path) -> bool:
    """把四仓快进到远端最新（只做 --ff-only，不产生合并提交）。

    源端（双系统 Linux 侧）可能落后远端较多：实测 bms 曾落后 204 个提交，
    其中含 pytest 启动插件、覆盖率采集等测试基础设施改动——不同步则测试结论不可信。
    """
    repos = ("", "bms", "biz", "mdm", "test")
    ok = True
    for name in repos:
        path = workspace / name if name else workspace
        label = name or "工作区"
        if not (path / ".git").exists():
            log(f"跳过 {label}（非 git 仓库）")
            continue
        proc = run(
            ("git", "-C", str(path), "pull", "--ff-only", "origin", "main"),
            check=False,
            capture=True,
        )
        head = run(
            ("git", "-C", str(path), "rev-parse", "--short", "HEAD"),
            check=False,
            capture=True,
        )
        short = head.stdout.strip() or "?"
        if proc.returncode == 0:
            log(f"{label} 已同步 -> {short}")
        else:
            ok = False
            log(f"{label} 同步失败：{proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else '未知错误'}")
    return ok


def reinstall_deps(workspace: Path) -> bool:
    """按锁文件重装依赖并重新外置（依赖锁文件随代码同步会变，必须跟着重装）。

    顺序与 bms/scripts/tools/deps/ 的约定一致：
      还原依赖（外置 -> 原位）-> uv sync / pnpm install --frozen-lockfile -> 外置依赖。
    """
    bms = workspace / "bms"
    deps_dir = bms / "scripts/tools/deps"
    if not deps_dir.is_dir():
        log("跳过依赖重装（未找到 scripts/tools/deps/）")
        return True

    steps = (
        ("还原依赖", ("bash", str(deps_dir / "还原依赖.sh"))),
        ("uv sync", ("uv", "sync", "--frozen")),
        ("pnpm install", ("pnpm", "install", "--frozen-lockfile")),
        ("外置依赖", ("bash", str(deps_dir / "外置依赖.sh"))),
    )
    for label, cmd in steps:
        cwd = bms / "backend" if label == "uv sync" else bms
        log(f"依赖重装：{label} ...")
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
            log(f"依赖重装失败于「{label}」：")
            for line in tail:
                log(f"  {line}")
            return False
    return True


def main(
    argv: list[str] | None = None,  # bare-collections:allow argparse 入参协议
) -> int:
    parser = argparse.ArgumentParser(
        description="在 WSL 内复刻 bizs 开发环境（从只读挂载的双系统 Ubuntu 盘复制）",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"源 home 目录（默认 {DEFAULT_SOURCE}）",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="只复制工作区，不复制依赖仓（约 1.3 GB）",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="跳过复制后的导入自检",
    )
    parser.add_argument(
        "--configs-only",
        action="store_true",
        help="只复制用户级配置（工作区已就绪时用）",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="复制后把四仓同步到远端最新，并按锁文件重装依赖（推荐：源端可能落后远端较多）",
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="跳过复制，只做 --sync（工作区已存在时刷新到最新）",
    )
    args = parser.parse_args(argv)

    err = check_prereqs()
    if err:
        return fail(err)

    source: Path = args.source
    err = check_source(source)
    if err:
        return fail(err)

    home = Path.home()
    workspace = home / "develop/bizs"

    log(f"源端 {source}（只读），目标 {workspace}")

    if not args.configs_only and not args.sync_only:
        # 1) 工作区（排除本地产物）
        sync_tree(source / "develop/bizs", workspace, WORKSPACE_EXCLUDES)

        # 2) 依赖仓
        if not args.skip_deps:
            for sub in DEPS_SUBDIRS:
                src_sub = source / "dev-deps" / sub
                if src_sub.is_dir():
                    sync_tree(src_sub, home / "dev-deps" / sub)
        else:
            log("按 --skip-deps 跳过依赖仓复制")

        # 3) 临时产物目录（空目录）
        for rel in ("tmp", ".playwright-mcp", ".playwright-cli"):
            (workspace / rel).mkdir(parents=True, exist_ok=True)

    # 3.5) 同步到远端最新 + 按锁文件重装依赖（源端可能落后远端较多）
    if args.sync or args.sync_only:
        if not sync_repos(workspace):
            return fail("仓库同步失败（可能有本地改动或冲突），请先手工处理后重跑")
        if not reinstall_deps(workspace):
            return fail("依赖重装失败，请按上面的报错处理")

    # 4) 用户级配置
    copied = copy_user_configs(source)
    log(f"已复制用户级配置：{', '.join(copied) if copied else '（无）'}")

    # 5) venv python 软链（venv 的 shebang 依赖它）
    if ensure_python_shim():
        log("已创建 /usr/local/bin/python -> /usr/bin/python3（需 root，已成功）")
    elif not Path("/usr/local/bin/python").exists():
        log("警告：/usr/local/bin/python 缺失且无法自动创建，请手动执行：")
        log("  sudo ln -sfn /usr/bin/python3 /usr/local/bin/python")

    # 6) 自检
    if not args.skip_verify:
        log("开始自检 ...")
        ok_b, msg_b = verify_backend(workspace)
        print(f"  [{'通过' if ok_b else '失败'}] {msg_b}")
        ok_f, msg_f = verify_frontend(workspace)
        print(f"  [{'通过' if ok_f else '失败'}] {msg_f}")
        if not (ok_b and ok_f):
            log("自检未全通过。依赖可能不兼容，可加 --sync 重装依赖，或手工执行：")
            log("  cd ~/develop/bizs/bms && bash scripts/tools/deps/还原依赖.sh")
            log("  cd backend && uv sync --frozen")
            log("  cd .. && pnpm install --frozen-lockfile")
            log("  bash scripts/tools/deps/外置依赖.sh")
            return 1

    log("工具版本：")
    report_versions()
    log("完成。进入环境：wsl -d Ubuntu-26.04 -- bash -lc 'cd ~/develop/bizs/bms && bash -l'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
