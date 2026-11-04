#!/usr/bin/env python3
"""修复 IDE「源代码管理（git）」面板看不到仓库的问题（VS Code / CodeBuddy 通用，Linux / Windows 双平台）。

## 现象

多仓库工作区（如 bizs：根 + bms / biz / mdm / msg / test 等）里，源代码管理面板只显示
其中一个仓库（常见是空仓库，于是面板看起来「没有变化」），或者「仓库」视图整块消失、
只剩「更改」——而「更改」只列 IDE 认定的活动仓库。

## 根因

**不是 git 故障**，而是 IDE 的**视图状态**里「哪些仓库可见 / 仓库视图是否显示」被改窄了。
故障可能独立出现在两处（两处都要通才算正常）：

**判据①** 工作区库 `<用户数据目录>/User/workspaceStorage/<hash>/state.vscdb` 的
`scm:view:visibleRepositories`：`visible` 只含部分下标，其余仓库被排除。

**判据②** 全局库 `<用户数据目录>/User/globalStorage/state.vscdb` 的
`workbench.scm.views.state.hidden`：`workbench.scm.repositories` 的 `isHidden` 为
`true` 时，面板「仓库」视图整块消失、只剩「更改」，而「更改」只列活动仓库。

`visible` 存的是 `all` 数组的**下标**，不是仓库名。排查时按 `all` 的顺序逐条对照，
即可看出被排除的是哪个仓库。

`<hash>` 目录按同目录 `workspace.json` 的 `folder`（裸目录打开）或 `workspace`
（`.code-workspace` 打开）字段定位；两种打开方式**各存一份状态库**，本脚本两处都认、
都修。URI 里的 `%3A` 百分号编码与 Windows 盘符大小写差异已做归一化比较。

> **易误判**：工作区库里 `workbench.scm.views.state` 三个视图的 `isHidden: true` 是
> IDE 的**正常默认值**（本机实测多个工作区三项全 true，面板照常显示），不参与判故障；
> 只有**全局库** `workbench.scm.views.state.hidden` 里 `workbench.scm.repositories`
> 为 true 才是故障（见 `ScmState.ok`）。

## 用法

**修复必须先完全退出目标 IDE**（含全部窗口）：IDE 运行期间改库，退出时会把内存里的
旧状态回写，覆盖本脚本的修改。脚本自身会检测进程并中止。

    # VS Code / CodeBuddy（默认 VS Code）
    python3 scripts/tools/ide/fix_scm_state.py --ide vscode
    python3 scripts/tools/ide/fix_scm_state.py --ide codebuddy

    # Windows 侧同一入口（用户数据目录自动取 %APPDATA%；也可显式指定）
    python backend/.venv/Scripts/python.exe scripts/tools/ide/fix_scm_state.py --ide codebuddy
    python3 scripts/tools/ide/fix_scm_state.py --ide codebuddy --user-data-dir "$APPDATA/CodeBuddy CN"

    # 指定工作区（默认取当前目录；可给目录，也可直接给 .code-workspace 文件）
    python3 scripts/tools/ide/fix_scm_state.py --ide vscode --workspace /home/minjian/develop/bizs

    # 只看现状、不改（可随时跑，无需退出 IDE）
    python3 scripts/tools/ide/fix_scm_state.py --ide vscode --check

退出码：0 正常或已修复；1 定位失败 / IDE 仍在运行 / 校验未通过；2 `--check` 判定为故障。

## 备选手段（不想改数据库时）

命令面板 →「视图: 重置视图位置」（View: Reset View Locations）；仓库选择器
（面板顶部的仓库名）里手动勾回全部仓库。

## 预防

用户设置加 `"scm.alwaysShowRepositories": true`（让仓库始终在源代码管理视图中
可见）可降低复发概率，但**不能完全防止**——实测加了仍会复发（2026-11-04 本机复发，
7 个仓库退化为 `visible: [6]` 且全局库仓库视图再次隐藏），届时重跑本脚本。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, cast
from urllib.parse import unquote, urlparse

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402


class IdeProfile(NamedTuple):
    """一个 IDE 的定位信息（Linux / Windows 各一套口径）。"""

    label: str
    linux_user_data_dir: str  # 相对 $HOME
    windows_user_data_dir: str  # 相对 %APPDATA%
    linux_process_markers: ConcurrentStableList[str]  # 进程命令行里出现即视为「该 IDE 在运行」
    windows_process_names: ConcurrentStableList[str]  # tasklist 映像名（含 .exe）


class ScmState(NamedTuple):
    """某工作区当前的 SCM 面板状态（工作区库 + 全局库合并后的判据）。"""

    hidden_views: ConcurrentStableList[str]
    all_repos: ConcurrentStableList[str]
    visible: ConcurrentStableList[int]
    global_repo_view_hidden: bool

    @property
    def has_repos(self) -> bool:
        """该工作区是否保存过仓库可见性记录。

        没保存过（键不存在）不等于故障——例如 bms_other 是 git 仓库但从未让 IDE
        写过该键；这类工作区只报告「不适用」，不判失败、也不提供修复。
        """
        return bool(self.all_repos)

    @property
    def visible_complete(self) -> bool:
        """工作区库里「全部仓库可见」是否成立（判据①）。"""
        return self.has_repos and len(self.visible) == len(self.all_repos)

    @property
    def ok(self) -> bool:
        """两处判据同时成立才算正常。

        **判据①**：工作区库 `visible` 覆盖 `all`（见 `visible_complete`）。
        **判据②**：全局库 `workbench.scm.views.state.hidden` 里 `workbench.scm.repositories`
        未被隐藏。工作区库里 `workbench.scm.views.state` 各视图 `isHidden: true` 是
        VS Code / CodeBuddy 的**正常默认值**（实测 CodeBuddy 的 bms_other / cws / Claw
        等工作区三项全为 true，面板照常显示变更），故**不**作为故障判据——早期版本
        拿它判失败，导致正常的工作区被误报。
        """
        return self.visible_complete and not self.global_repo_view_hidden


# 各 IDE 的默认用户数据目录与进程特征（Linux / Windows 各一套）
IDE_PROFILES: ConcurrentStableList[tuple[str, IdeProfile]] = ConcurrentStableList(
    (
        (
            "vscode",
            IdeProfile(
                label="VS Code",
                linux_user_data_dir=".config/Code",
                windows_user_data_dir="Code",
                linux_process_markers=ConcurrentStableList(("/usr/share/code/code",)),
                windows_process_names=ConcurrentStableList(("Code.exe",)),
            ),
        ),
        (
            "codebuddy",
            IdeProfile(
                label="CodeBuddy",
                linux_user_data_dir=".config/CodeBuddy CN",
                windows_user_data_dir="CodeBuddy CN",
                linux_process_markers=ConcurrentStableList(("/usr/share/buddycn/",)),
                windows_process_names=ConcurrentStableList(("CodeBuddy CN.exe",)),
            ),
        ),
    )
)

VIEW_STATE_KEY = "workbench.scm.views.state"
REPOS_KEY = "scm:view:visibleRepositories"
HIDDEN_VIEWS_KEY = "workbench.scm.views.state.hidden"
REPO_VIEW_ID = "workbench.scm.repositories"


def default_user_data_dir(profile: IdeProfile) -> Path:
    """按平台取 IDE 用户数据目录：Windows 走 %APPDATA%，其余走 $HOME。"""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home()) / profile.windows_user_data_dir
    return Path.home() / profile.linux_user_data_dir


def read_value(cur: sqlite3.Cursor, key: str) -> tuple[str | None, bool]:
    """读一个 ItemTable 值；返回 (文本, 原值是否为 bytes)。"""
    cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        return None, False
    value = row[0]
    if isinstance(value, bytes):
        return value.decode("utf-8"), True
    return value, False


def write_value(cur: sqlite3.Cursor, key: str, obj: object, as_bytes: bool) -> None:
    """按原存储类型写回（bytes 就写 bytes，避免 IDE 读不出来）。"""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    cur.execute(
        "UPDATE ItemTable SET value=? WHERE key=?",
        (text.encode("utf-8") if as_bytes else text, key),
    )


def uri_matches_workspace(uri: str, workspace: Path) -> bool:
    """判断 workspace.json 里的 URI 是否指向目标工作区（目录或其 `.code-workspace` 文件）。

    两种打开方式存两种形态：裸目录打开写 `folder`，`--workspace` 打开写 `workspace`
    （指向 `.code-workspace` 文件）。URI 需解 `%3A` 百分号编码（Windows 盘符写成
    `file:///d%3A/...`），并靠 `Path` 比较吃掉 Windows 的盘符大小写与斜杠差异。
    """
    parsed = urlparse(uri)
    if parsed.scheme not in ("file", ""):
        return False
    raw = unquote(parsed.path)
    if os.name == "nt" and raw[:1] == "/" and raw[2:3] == ":":
        raw = raw[1:]
    if not raw:
        return False
    try:
        candidate = Path(raw).resolve()
        target = workspace.resolve()
    except OSError:
        return False
    return candidate == target or candidate.parent == target


def find_workspace_dbs(user_data_dir: Path, workspace: Path) -> ConcurrentStableList[Path]:
    """定位该工作区的全部 state.vscdb（裸目录与 `.code-workspace` 打开各一份）。"""
    found: ConcurrentStableList[Path] = ConcurrentStableList()
    storage = user_data_dir / "User" / "workspaceStorage"
    if not storage.is_dir():
        return found
    for entry in sorted(storage.iterdir()):
        ws_json, db = entry / "workspace.json", entry / "state.vscdb"
        if not (ws_json.is_file() and db.is_file()):
            continue
        try:
            meta = json.loads(ws_json.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        for field in ("folder", "workspace"):
            uri = meta.get(field)
            if isinstance(uri, str) and uri_matches_workspace(uri, workspace):
                found.add(db)
                break
    return found


def _running_by_cmdline(markers: Iterable[str]) -> bool:
    """Linux：`ps -eo args` 里出现特征命令行即视为在运行。"""
    try:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=10).stdout
    except OSError, subprocess.SubprocessError:
        return False
    return any(any(marker in line for marker in markers) and "fix_scm_state" not in line for line in out.splitlines())


def _running_by_image_name(names: Iterable[str]) -> bool:
    """Windows：`tasklist` 映像名命中即视为在运行（参数里可能带空格，用 CSV 解析）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        ).stdout
    except OSError, subprocess.SubprocessError:
        return False
    wanted = {name.casefold() for name in names}
    for line in out.splitlines():
        if not line.strip().startswith('"'):
            continue
        image = line.split('","')[0].strip().strip('"')
        if image.casefold() in wanted:
            return True
    return False


def ide_running(profile: IdeProfile) -> bool:
    """目标 IDE 是否仍有进程在跑（运行中改库会被退出回写覆盖）。"""
    if os.name == "nt":
        return _running_by_image_name(profile.windows_process_names)
    return _running_by_cmdline(profile.linux_process_markers)


def _hidden_view_names(raw: str) -> ConcurrentStableList[str]:
    """从工作区库 `workbench.scm.views.state` 取 `isHidden` 为真的视图名（仅打印用）。"""
    names: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        data = json.loads(raw)
    except ValueError:
        return names
    if not isinstance(data, dict):
        return names
    for name, raw_view in cast("dict[str, object]", data).items():
        if isinstance(raw_view, dict) and cast("dict[str, object]", raw_view).get("isHidden"):
            names.add(name)
    return names


def _repo_lists(raw: str) -> tuple[ConcurrentStableList[str], ConcurrentStableList[int]]:
    """从工作区库 `scm:view:visibleRepositories` 取 (全部仓库, 可见下标)。"""
    all_repos: ConcurrentStableList[str] = ConcurrentStableList()
    visible: ConcurrentStableList[int] = ConcurrentStableList()
    try:
        data = json.loads(raw)
    except ValueError:
        return all_repos, visible
    if not isinstance(data, dict):
        return all_repos, visible
    fields = cast("dict[str, object]", data)
    for repo in cast("list[object]", fields.get("all") or []):
        if isinstance(repo, str):
            all_repos.add(repo)
    for index in cast("list[object]", fields.get("visible") or []):
        if isinstance(index, int):
            visible.add(index)
    return all_repos, visible


def _hidden_view_entries(raw: str) -> ConcurrentStableList[object]:
    """从全局库 `workbench.scm.views.state.hidden` 取「视图条目」数组。"""
    entries: ConcurrentStableList[object] = ConcurrentStableList()
    try:
        data = json.loads(raw)
    except ValueError:
        return entries
    if not isinstance(data, list):
        return entries
    entries.extend(cast("list[object]", data))
    return entries


def _is_hidden_repo_view(raw_entry: object) -> bool:
    """该视图条目是否就是「仓库」视图且被隐藏。"""
    if not isinstance(raw_entry, dict):
        return False
    entry = cast("dict[str, object]", raw_entry)
    return entry.get("id") == REPO_VIEW_ID and bool(entry.get("isHidden"))


def read_global_repo_view_hidden(cur: sqlite3.Cursor) -> bool:
    """全局库「仓库」视图是否被隐藏（判据②）。库/键缺失一律视为未隐藏。"""
    raw, _ = read_value(cur, HIDDEN_VIEWS_KEY)
    if not raw:
        return False
    return any(_is_hidden_repo_view(entry) for entry in _hidden_view_entries(raw))


def global_repo_view_hidden(global_db: Path) -> bool:
    """只读打开全局库并判定「仓库」视图是否隐藏；库缺失视为未隐藏。"""
    if not global_db.is_file():
        return False
    con = _open(global_db, readonly=True)
    try:
        return read_global_repo_view_hidden(con.cursor())
    finally:
        con.close()


def inspect(cur: sqlite3.Cursor, repo_view_hidden: bool = False) -> ScmState:
    """读工作区库当前状态，供 --check 与修复前后对照。"""
    hidden: ConcurrentStableList[str] = ConcurrentStableList()
    raw, _ = read_value(cur, VIEW_STATE_KEY)
    if raw:
        hidden.extend(_hidden_view_names(raw))

    all_repos: ConcurrentStableList[str] = ConcurrentStableList()
    visible: ConcurrentStableList[int] = ConcurrentStableList()
    raw, _ = read_value(cur, REPOS_KEY)
    if raw:
        all_repos, visible = _repo_lists(raw)

    return ScmState(
        hidden_views=hidden,
        all_repos=all_repos,
        visible=visible,
        global_repo_view_hidden=repo_view_hidden,
    )


def describe(state: ScmState) -> None:
    """打印状态明细（仓库逐条标出可见与否）。"""
    hidden = ", ".join(state.hidden_views) if state.hidden_views else "无"
    print(f"      工作区库视图 isHidden：{hidden}（正常默认值，不参与判故障）")
    print(f"      全局库仓库视图      ：{'已隐藏（故障）' if state.global_repo_view_hidden else '显示'}")
    print(f"      仓库总数  ：{len(state.all_repos)}，可见下标：{list(state.visible)}")
    for index, repo in enumerate(state.all_repos):
        mark = "✓" if index in state.visible else "✗"
        print(f"        {mark} [{index}] {repo.split('file://')[-1] or repo}")


def _apply_workspace_fix(cur: sqlite3.Cursor) -> ConcurrentStableList[str]:
    """把工作区库的仓库可见性改回「全部可见」（判据①）。

    只改 `scm:view:visibleRepositories`——`workbench.scm.views.state` 的 `isHidden`
    是正常默认值（见 `ScmState.ok`），不予改动，避免无谓的状态写入。
    """
    changed: ConcurrentStableList[str] = ConcurrentStableList()

    raw, as_bytes = read_value(cur, REPOS_KEY)
    if not raw:
        return changed
    try:
        data = json.loads(raw)
    except ValueError:
        return changed
    if not isinstance(data, dict):
        return changed
    fields = cast("dict[str, object]", data)
    all_repos = cast("list[object]", fields.get("all") or [])
    visible = cast("list[object]", fields.get("visible") or [])
    if all_repos and len(visible) != len(all_repos):
        fields["visible"] = list(range(len(all_repos)))
        write_value(cur, REPOS_KEY, fields, as_bytes)
        changed.add(f"工作区库：恢复 {len(all_repos)} 个仓库可见")

    return changed


def _apply_global_fix(cur: sqlite3.Cursor) -> ConcurrentStableList[str]:
    """把全局库的「仓库」视图取消隐藏（判据②）。"""
    changed: ConcurrentStableList[str] = ConcurrentStableList()

    raw, as_bytes = read_value(cur, HIDDEN_VIEWS_KEY)
    if not raw:
        return changed
    items = _hidden_view_entries(raw)
    touched = False
    for raw_entry in items:
        if not isinstance(raw_entry, dict):
            continue
        entry = cast("dict[str, object]", raw_entry)
        if entry.get("id") == REPO_VIEW_ID and entry.get("isHidden"):
            entry["isHidden"] = False
            touched = True
    if touched:
        write_value(cur, HIDDEN_VIEWS_KEY, list(items), as_bytes)
        changed.add("全局库：取消隐藏「仓库」视图")

    return changed


def _open(db: Path, readonly: bool) -> sqlite3.Connection:
    """打开状态库；只读模式（--check）可在 IDE 运行期间安全使用。"""
    if readonly:
        return sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    return sqlite3.connect(str(db))


def _backup(db: Path, stamp: str) -> Path:
    """备份状态库（旁挂 .bak-<时间戳>，便于回滚）。"""
    backup = db.with_name(f"{db.name}.bak-{stamp}")
    shutil.copy2(db, backup)
    return backup


def main() -> int:
    profiles = dict(IDE_PROFILES)
    parser = argparse.ArgumentParser(
        description="修复 IDE 源代码管理面板看不到仓库（工作区可见性不全 / 仓库视图被隐藏）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ide",
        choices=sorted(profiles),
        default="vscode",
        help="目标 IDE（默认 vscode）",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="工作区目录或 .code-workspace 文件（默认当前目录），用于定位 workspaceStorage 下的 hash 目录",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="IDE 用户数据目录（默认按 --ide 取平台标准位置：Windows %%APPDATA%%、其余 $HOME）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只查看当前状态，不做修改（无需退出 IDE）",
    )
    args = parser.parse_args()

    profile = profiles[args.ide]
    user_data_dir = Path(args.user_data_dir).expanduser() if args.user_data_dir else default_user_data_dir(profile)
    workspace = Path(args.workspace).expanduser().resolve()
    if workspace.is_file():
        workspace = workspace.parent

    print(f"[目标] {profile.label}")
    print(f"       工作区     ：{workspace}")
    print(f"       用户数据目录：{user_data_dir}")

    if not user_data_dir.is_dir():
        print(f"[失败] 用户数据目录不存在：{user_data_dir}")
        return 1

    dbs = find_workspace_dbs(user_data_dir, workspace)
    if not dbs:
        print(
            f"[失败] 未找到该工作区的 state.vscdb。\n"
            f"       确认「{workspace}」曾用 {profile.label} 打开过，"
            f"或用 --user-data-dir 指定目录。"
        )
        return 1

    global_db = user_data_dir / "User" / "globalStorage" / "state.vscdb"
    global_hidden = global_repo_view_hidden(global_db)

    if not args.check and ide_running(profile):
        print(
            f"\n[中止] 检测到 {profile.label} 仍在运行。\n"
            f"       运行期间改库会被退出时的内存回写覆盖，"
            f"请**完全退出**（含所有窗口）后重跑。"
        )
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups: ConcurrentStableList[Path] = ConcurrentStableList()
    changed: ConcurrentStableList[str] = ConcurrentStableList()

    for db in dbs:
        print(f"\n[状态库] {db}")
        con = _open(db, readonly=args.check)
        cur = con.cursor()
        before = inspect(cur, global_hidden)

        print("\n[现状]")
        describe(before)

        if args.check:
            con.close()
            if not before.has_repos:
                print("\n[结论] 该工作区未保存过仓库可见性记录（不适用，无需处理）。")
                continue
            if before.ok:
                print("\n[结论] 面板状态正常。")
                continue
            print("\n[结论] 面板状态异常（见上方 ✗ / 全局库隐藏标记），去掉 --check 即可修复。")
            return 2

        if not before.has_repos and not global_hidden:
            con.close()
            print("\n[完成] 该工作区未保存过仓库可见性记录（可能是未含 git 仓库，或尚未让 IDE 写过该键），无需处理。")
            continue

        if not before.ok:
            backups.add(_backup(db, stamp))
            if global_db.is_file():
                backups.add(_backup(global_db, stamp))
            changed.extend(_apply_workspace_fix(cur))

        if global_hidden and global_db.is_file():
            g_write = _open(global_db, readonly=False)
            changed.extend(_apply_global_fix(g_write.cursor()))
            g_write.commit()
            g_write.close()

        con.commit()
        after = inspect(cur, global_repo_view_hidden(global_db))
        con.close()

        print("\n[修复后]")
        describe(after)
        if after.ok:
            print(f"\n[完成] 校验通过。重新打开 {profile.label}，源代码管理面板即可看到全部仓库。")
        else:
            print("\n[警告] 校验未通过，请检查上面的状态输出。")
            return 1

    if changed:
        print("\n[改动]")
        for line in changed:
            print(f"      - {line}")
    if backups:
        print("\n[备份]")
        for backup in backups:
            print(f"      - {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
