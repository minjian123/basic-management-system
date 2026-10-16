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
"""

import contextlib
import errno
import os
import shutil
import stat
import subprocess
import sys

IS_WINDOWS = os.name == "nt"
_REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
# Windows 重解析点目标可能带的内核前缀（readlink 返回值）
_WIN_TARGET_PREFIXES = ("\\\\?\\", "\\??\\")


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


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


def resolve_deps_dir(root):
    """本地依赖仓目录：环境变量 DEPS_DIR > deploy/.env 的 DEPS_DIR= > 缺省 $HOME/dev-deps/bms。"""
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
