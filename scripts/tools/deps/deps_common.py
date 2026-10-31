#!/usr/bin/env python3
"""依赖外置工具链共用实现（Linux / Windows 双平台，仅用 Python 3 标准库）。

三份入口脚本（外置依赖.py / 还原依赖.py / 重装依赖.py）共用本模块；
Linux 的同名 .sh 与 Windows 的同名 .bat 均为「转调同名 .py」的瘦包装——
单一实现避免双平台漂移（2026-10-16 起；此前 Linux 为独立 shell 实现）。

平台链接口径：
- Linux：绝对路径符号链接（与历史 shell 实现一致）；
- Windows：目录联接 junction（mklink /J，免管理员即可创建，工具兼容面广）。

本地依赖仓目录（本地资源信息，不入公开文档）：
  1) 环境变量 DEPS_DIR；
  2) bms/deploy/.env 中的 DEPS_DIR=；
  3) 缺省 $HOME/dev-deps/bms。

**平台分目录（2026-10-31 事故后加固）**：依赖根下再按平台分一层
（`<DEPS_DIR>/windows` 或 `<DEPS_DIR>/linux`），并在目录内落 `.platform` 标识。
Windows 与 WSL 共用同一 `DEPS_DIR`（同一份 `deploy/.env`）时，两边的 venv / node_modules
落在不同子目录，**即使有人绕过脚本直接 `uv sync`，也只会写坏自己平台那份**；
脚本侧再用 `.platform` 与 `pyvenv.cfg` 双重校验，跨平台误用直接拒绝。
"""

import contextlib
import errno
import io
import os
import shutil
import stat
import subprocess
import sys
from typing import cast

IS_WINDOWS = os.name == "nt"
_REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
# Windows 重解析点目标可能带的内核前缀（readlink 返回值）
_WIN_TARGET_PREFIXES = ("\\\\?\\", "\\??\\")


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            cast("io.TextIOWrapper", stream).reconfigure(encoding="utf-8")


def norm(path):
    """路径规范化（Windows 大小写不敏感、分隔符统一），用于比较。"""
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


def find_repo_root(script_file, prefix):
    """定位仓库根（脚本位于 <根>/scripts/tools/deps/ 下，上跳三级即根）。

    路径前缀重复（如已进入 bms 仓又写成 `bms/scripts/...`）会把根推深一层，
    后续建链 / 搬移都会落进幽灵目录——此处就地快速失败，不做任何动作。
    """
    here = os.path.dirname(os.path.realpath(os.fspath(script_file)))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    if not os.path.isfile(os.path.join(root, "pnpm-workspace.yaml")):
        sys.stderr.write(f"[{prefix}] 仓库根定位失败：{root} 下没有 pnpm-workspace.yaml\n")
        sys.stderr.write(f"[{prefix}] 请在 bms 仓根执行脚本，勿叠加仓名前缀。\n")
        sys.exit(2)
    return root


PLATFORM_TAG = "windows" if IS_WINDOWS else ("linux" if sys.platform.startswith("linux") else sys.platform)
"""本平台标签（依赖仓子目录名与 `.platform` 标识取值）。"""

PLATFORM_MARKER = ".platform"
"""依赖仓内的平台标识文件名（内容即 `PLATFORM_TAG`）。"""

LEGACY_ENTRIES = ("backend-venv", "node_modules", "frontend")
"""平台分目录改造前的依赖仓顶层条目（一次性迁移的对象）。"""


def resolve_deps_root(root):
    """依赖仓**根**：环境变量 DEPS_DIR > deploy/.env 的 DEPS_DIR= > 缺省 $HOME/dev-deps/bms。"""
    value = os.environ.get("DEPS_DIR", "").strip()
    if value:
        return os.path.abspath(os.path.expanduser(value))
    env_file = os.path.join(root, "deploy", ".env")
    if os.path.isfile(env_file):
        try:
            with open(env_file, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith("DEPS_DIR="):
                        value = line[len("DEPS_DIR=") :].strip()
                        if value:
                            return os.path.abspath(os.path.expanduser(value))
        except OSError:
            pass
    return os.path.abspath(os.path.join(os.path.expanduser("~"), "dev-deps", "bms"))


def migrate_legacy_layout(base):
    """把平台分目录改造前的顶层依赖条目搬进 `<base>/<PLATFORM_TAG>/`（幂等）。

    - 目标已存在同名条目：保留目标、跳过（不覆盖，避免把刚装好的环境换回旧版）；
    - venv 由另一平台创建：不搬移（跨平台结构不兼容）。

    Returns:
        搬移 / 跳过的说明列表（供调用方打印）。
    """
    notes = []
    if not os.path.isdir(base):
        return notes
    target = os.path.join(base, PLATFORM_TAG)
    for name in LEGACY_ENTRIES:
        src = os.path.join(base, name)
        if not os.path.lexists(src):
            continue
        dest = os.path.join(target, name)
        if os.path.lexists(dest):
            notes.append(f"[迁移] 跳过 {name}：{PLATFORM_TAG} 目录已有同名条目")
            continue
        if name == "backend-venv" and venv_foreign(src):
            notes.append(f"[迁移] 跳过 backend-venv：{venv_foreign(src)}")
            continue
        os.makedirs(target, exist_ok=True)
        move_dir(src, dest)
        notes.append(f"[迁移] {name} -> {os.path.join(PLATFORM_TAG, name)}")
    return notes


def resolve_deps_dir(root):
    """本地依赖仓目录（**按平台分目录**）：`<根>/<windows|linux>`。

    平台分目录是硬隔离手段：Windows 与 WSL 共用同一 `DEPS_DIR` 时互不覆盖；
    老布局（依赖条目直接放在根下）在解析时一次性迁移，调用方无感。
    """
    base = resolve_deps_root(root)
    for note in migrate_legacy_layout(base):
        print(note)
    return os.path.join(base, PLATFORM_TAG)


def ensure_platform_marker(deps_dir, prefix):
    """校验并落平台标识（跨平台误用即拒；缺标识时写入）。"""
    os.makedirs(deps_dir, exist_ok=True)
    marker = os.path.join(deps_dir, PLATFORM_MARKER)
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8", errors="replace") as handle:
            recorded = handle.read().strip()
        if recorded and recorded != PLATFORM_TAG:
            sys.stderr.write(
                f"[{prefix}] 依赖仓 {deps_dir} 标注为 {recorded}，本平台是 {PLATFORM_TAG}，拒绝使用。\n"
                f"[{prefix}] 处置：为各平台使用独立 DEPS_DIR，或删掉该目录让本平台重建。\n"
            )
            sys.exit(2)
        return
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write(PLATFORM_TAG + "\n")


def validate_layout(root, deps_dir, prefix):
    """依赖仓与项目根不得互为前缀（错配时搬移/建链会互相污染），快速失败。"""
    r, d = norm(root), norm(deps_dir)
    if d == r or d.startswith(r + os.sep) or r.startswith(d + os.sep):
        sys.stderr.write(f"[{prefix}] 依赖仓（{deps_dir}）与项目根（{root}）互为前缀，定位异常，中止。\n")
        sys.exit(2)


def warn_cross_volume(root, deps_dir):
    """Windows 下跨盘搬移会退化为复制，给出提示。"""
    if not IS_WINDOWS:
        return
    root_drive = os.path.splitdrive(root)[0]
    deps_drive = os.path.splitdrive(deps_dir)[0]
    if root_drive and deps_drive and root_drive.lower() != deps_drive.lower():
        print(f"[提示] 依赖仓与项目不在同一盘（{root_drive} -> {deps_drive}）：搬移将退化为复制，耗时较长。")


# ---- 链接（重解析点）判定与操作 ----


def _is_reparse(path):
    """Windows：路径本身是否带重解析点属性（符号链接与 junction 都是 True）。"""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_FLAG)


def _entry_is_link(entry):
    """scandir 条目是否为链接（POSIX 符号链接；Windows 符号链接或 junction）。"""
    try:
        if entry.is_symlink():
            return True
        info = entry.stat(follow_symlinks=False)
    except OSError:
        return True  # 读不到的条目按链接处理跳过，避免误当待搬移目录
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_FLAG)


def is_link(path):
    """链接判定：POSIX 符号链接；Windows 下符号链接与 junction 均视为链接。"""
    return os.path.islink(path) or _is_reparse(path)


def link_target(path):
    """链接的解析目标（绝对路径字符串）；非链接 / 不可读返回 None。"""
    try:
        raw = os.readlink(path)
    except OSError:
        return None
    for prefix in _WIN_TARGET_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if not os.path.isabs(raw):
        raw = os.path.join(os.path.dirname(os.path.abspath(os.fspath(path))), raw)
    return os.path.normpath(raw)


def create_link(link, target):
    """建目录链接：Windows 用 junction（免管理员）；其余平台用绝对路径符号链接。"""
    link = os.path.abspath(os.fspath(link))
    target = os.path.abspath(os.fspath(target))
    parent = os.path.dirname(link)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if IS_WINDOWS:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise OSError(f"mklink /J 失败（exit={result.returncode}）：{link} -> {target} {detail}")
    else:
        os.symlink(target, link)


def remove_link(path):
    """只删链接本体、绝不穿透：Windows（junction / 目录符号链接）用 rmdir，失败回退 unlink。"""
    try:
        os.rmdir(path)
    except OSError:
        os.unlink(path)


def remove_path_safe(path):
    """删除路径：链接只删本体；真实目录才递归删除。"""
    if is_link(path):
        remove_link(path)
        return
    shutil.rmtree(path)


def move_dir(src, dst):
    """目录搬移：同分区 rename（秒级）；跨分区回退 shutil.move（复制+删除）。"""
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == 17:  # 17: ERROR_NOT_SAME_DEVICE
            shutil.move(src, dst)
        else:
            raise


def is_within(path, base):
    """path 是否位于 base 之内（含相等）。"""
    p, b = norm(path), norm(base)
    return p == b or p.startswith(b + os.sep)


# ---- venv 平台归属校验（防跨平台互相覆盖）----


def venv_home(venv_dir):
    """读 venv 的 `pyvenv.cfg` 中 `home=`（解释器所在目录）；缺失或不可读返回空串。"""
    config = os.path.join(os.fspath(venv_dir), "pyvenv.cfg")
    try:
        with open(config, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                key, _, value = line.partition("=")
                if key.strip().lower() == "home":
                    return value.strip()
    except OSError:
        return ""
    return ""


def venv_foreign(venv_dir):
    """判定 venv 是否由**另一平台**创建（跨平台共用同一路径会互相破坏结构）。

    背景（2026-10-26 排查）：WSL 侧 uv 经 `/mnt/d/...` 作用于同一个 `backend/.venv` 时，
    会把 `pyvenv.cfg` 的 `home` 写成 POSIX 路径（`/usr/local/bin`）并留下 Linux 专有的
    `lib64` 结构；回到 Windows 该 venv 即不可用，`uv run` 会重建，形成「反复被破坏」。

    判定依据 `home` 的形态（不用目录结构判定：Windows 侧 `ensure_venv_bin_shim` 会补
    `bin/` 硬链接，`bin` 与 `Scripts` 可能同时存在，结构不可靠）：

    - Windows：`home` 应为盘符路径（`C:\\...`）或 UNC（`\\\\...`）；
    - POSIX：`home` 应为 `/...`。

    Returns:
        空串表示与本平台一致（或无法判定，按一致处理，不阻断既有流程）；
        非空串为不匹配原因（供调用方打印与拒绝搬移）。
    """
    home = venv_home(venv_dir)
    if not home:
        return ""
    is_posix_path = home.startswith("/")
    if IS_WINDOWS and is_posix_path:
        return f"pyvenv.cfg 的 home 为 POSIX 路径（{home}），该 venv 由 Linux/WSL 侧创建"
    if not IS_WINDOWS and not is_posix_path:
        return f"pyvenv.cfg 的 home 为 Windows 路径（{home}），该 venv 由 Windows 侧创建"
    return ""


def reject_foreign_venv(venv_dir, prefix):
    """搬移 / 采用 venv 前校验平台归属：不匹配即提示并返回 True（调用方应跳过）。"""
    reason = venv_foreign(venv_dir)
    if not reason:
        return False
    sys.stderr.write(f"[{prefix}] 拒绝搬移 {venv_dir}：{reason}\n")
    sys.stderr.write(
        f"[{prefix}] 跨平台共用同一 .venv 会互相破坏结构。处置：在本平台重新创建环境"
        f"（删除该目录后按《uv部署使用说明》7.2 节重建），或为各平台使用独立依赖仓。\n"
    )
    return True


# ---- venv 解释器路径口径（Windows 兼容入口）----


def ensure_venv_bin_shim(venv_dir, prefix, dry_run=False):
    """Windows：为 venv 补 `bin/python` 兼容入口（→ Scripts/python.exe），幂等。

    背景：项目内解释器口径统一写 `backend/.venv/bin/python`（Linux 原生布局，跨平台一份
    配置）；而 Windows 上 uv 建的 venv 只有 `Scripts/python.exe`，没有 `bin/`。缺这一层会让
    Pylance / Ruff / python-envs 报「无法解析默认解释器路径 .../.venv/bin/python」。
    做法：在 venv 内建 `bin/python`（无扩展名，供字面路径使用）与 `bin/python.exe` 两个硬链接
    （同卷零拷贝；不支持硬链接时回退复制）。链接失效（uv sync 换过 python.exe）即重建。
    Linux / macOS 原生就有 `bin/python`，直接跳过。dry_run 时只报告不改动。
    """
    if not IS_WINDOWS:
        return
    scripts = os.path.join(venv_dir, "Scripts", "python.exe")
    if not os.path.isfile(scripts):
        return
    bin_dir = os.path.join(venv_dir, "bin")
    for name in ("python", "python.exe"):
        dest = os.path.join(bin_dir, name)
        if os.path.exists(dest):
            try:
                if os.path.samefile(scripts, dest):
                    continue  # 已指向当前解释器，无需重建
            except OSError:
                pass
            if dry_run:
                print(f"[dry-run] 重建解释器兼容入口 bin/{name}（硬链接 → Scripts/python.exe）")
                continue
            os.unlink(dest)
        elif dry_run:
            print(f"[dry-run] 补解释器兼容入口 bin/{name}（硬链接 → Scripts/python.exe）")
            continue
        os.makedirs(bin_dir, exist_ok=True)
        try:
            os.link(scripts, dest)
            print(f"[{prefix}] 补解释器兼容入口 bin/{name}（硬链接 → Scripts/python.exe）")
        except OSError:
            shutil.copy2(scripts, dest)
            print(f"[{prefix}] 补解释器兼容入口 bin/{name}（复制 → Scripts/python.exe）")


# ---- 目录扫描 ----


def find_node_modules_dirs(start):
    """枚举真实目录中的 node_modules（跳过链接；命中后不再深入，避开超长路径）。

    跳过项：重解析点（junction / 符号链接＝已外置标记或非依赖目录）、`.git`、`.pnpm`。
    """
    found = []
    stack = [os.path.abspath(os.fspath(start))]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if _entry_is_link(entry):
                continue
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if entry.name == "node_modules":
                found.append(entry.path)
                continue
            if entry.name in (".git", ".pnpm"):
                continue
            stack.append(entry.path)
    return sorted(found)


def find_reparse_points(start):
    """枚举依赖仓内的全部链接（工作区链接修复的候选）。

    `.pnpm` 内的链接必然指向含完整包体的目录（非修复候选），跳过以省扫描。
    """
    found = []
    stack = [os.path.abspath(os.fspath(start))]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if _entry_is_link(entry):
                found.append(entry.path)
                continue
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if entry.name == ".pnpm":
                continue
            stack.append(entry.path)
    return found
