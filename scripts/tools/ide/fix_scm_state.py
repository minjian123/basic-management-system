#!/usr/bin/env python3
"""修复 IDE「源代码管理（git）」面板看不到仓库的问题（VS Code / CodeBuddy 通用）。

## 现象

多仓库工作区（如 bizs：根 + bms / biz / mdm / test 共 5 个仓库）里，源代码管理
面板只显示其中一个仓库（常见是空仓库，于是面板看起来「没有变化」），或者
「更改」「仓库」「图表」等视图整块消失。

## 根因

**不是 git 故障**，而是 IDE 的**工作区状态**里「哪些仓库可见」被改窄了。权威存储在：

    <用户数据目录>/User/workspaceStorage/<hash>/state.vscdb

（SQLite；`<hash>` 目录按同目录 `workspace.json` 的 `folder` 字段定位。）关键键：

| 键 | 说明 |
| --- | --- |
| `scm:view:visibleRepositories` | **故障就在这个键**：`visible` 只含部分下标，有变更的仓库被排除 |
| `workbench.scm.views.state` | `isHidden: true` 是正常默认值，不参与判故障（见 `ScmState.ok`） |

`visible` 存的是 `all` 数组的**下标**，不是仓库名。排查时按 `all` 的顺序逐条对照，
即可看出被排除的是哪个仓库。

## 用法

**必须先完全退出目标 IDE**（含全部窗口）：IDE 运行期间改库，退出时会把内存里的
旧状态回写，覆盖本脚本的修改。

    # VS Code（默认；自动探测 ~/.config/Code）
    python3 scripts/tools/ide/fix_scm_state.py --ide vscode

    # CodeBuddy
    python3 scripts/tools/ide/fix_scm_state.py --ide codebuddy

    # 指定工作区（默认取当前目录）与用户数据目录
    python3 scripts/tools/ide/fix_scm_state.py --ide vscode \
        --workspace /home/minjian/develop/bizs \
        --user-data-dir "$HOME/.config/Code"

    # 只看现状、不改（可随时跑，无需退出 IDE）
    python3 scripts/tools/ide/fix_scm_state.py --ide vscode --check

## 备选手段（不想改数据库时）

命令面板 →「视图: 重置视图位置」（View: Reset View Locations）；仓库选择器
（面板顶部的仓库名）里手动勾回全部仓库。

## 预防

用户设置加 `"scm.alwaysShowRepositories": true`（让仓库始终在源代码管理视图中
可见）可降低复发概率，但**不能完全防止**——视图仍可能被手动隐藏，届时重跑本脚本。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402


class IdeProfile(NamedTuple):
    """一个 IDE 的定位信息。"""

    label: str
    user_data_dir: str  # 相对 $HOME
    process_markers: tuple[str, ...]  # 进程命令行里出现即视为「该 IDE 在运行」


class ScmState(NamedTuple):
    """某工作区当前的 SCM 面板状态。"""

    hidden_views: tuple[str, ...]
    all_repos: tuple[str, ...]
    visible: tuple[int, ...]

    @property
    def has_repos(self) -> bool:
        """该工作区是否保存过仓库可见性记录。

        没保存过（键不存在）不等于故障——例如 bms_other 是 git 仓库但从未让 IDE
        写过该键；这类工作区只报告「不适用」，不判失败、也不提供修复。
        """
        return bool(self.all_repos)

    @property
    def ok(self) -> bool:
        """全部仓库可见即视为正常。

        **判据只看 `visible` 是否覆盖 `all`**：`workbench.scm.views.state` 里各视图
        `isHidden: true` 是 VS Code / CodeBuddy 的**正常默认值**（实测 CodeBuddy 的
        bms_other / cws / Claw 等工作区三项全为 true，面板照常显示变更），故不作为
        故障判据——早期版本拿它判失败，导致正常的工作区被误报。
        """
        return self.has_repos and len(self.visible) == len(self.all_repos)


# 各 IDE 的默认用户数据目录（相对 $HOME）与进程特征
IDE_PROFILES: tuple[tuple[str, IdeProfile], ...] = (
    (
        "vscode",
        IdeProfile(
            label="VS Code",
            user_data_dir=".config/Code",
            process_markers=("/usr/share/code/code",),
        ),
    ),
    (
        "codebuddy",
        IdeProfile(
            label="CodeBuddy",
            user_data_dir=".config/CodeBuddy CN",
            process_markers=("/usr/share/buddycn/",),
        ),
    ),
)

VIEW_STATE_KEY = "workbench.scm.views.state"
REPOS_KEY = "scm:view:visibleRepositories"


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


def find_workspace_db(user_data_dir: Path, folder_uri: str) -> Path | None:
    """按 workspace.json 的 folder 字段定位工作区的 state.vscdb。"""
    storage = user_data_dir / "User" / "workspaceStorage"
    if not storage.is_dir():
        return None
    for entry in sorted(storage.iterdir()):
        ws_json, db = entry / "workspace.json", entry / "state.vscdb"
        if not (ws_json.is_file() and db.is_file()):
            continue
        try:
            meta = json.loads(ws_json.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        if meta.get("folder") == folder_uri:
            return db
    return None


def ide_running(markers: Iterable[str]) -> bool:
    """目标 IDE 是否仍有进程在跑（运行中改库会被退出回写覆盖）。"""
    try:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=10).stdout
    except OSError, subprocess.SubprocessError:
        return False
    return any(any(marker in line for marker in markers) and "fix_scm_state" not in line for line in out.splitlines())


def inspect(cur: sqlite3.Cursor) -> ScmState:
    """读当前状态，供 --check 与修复前后对照。"""
    hidden: ConcurrentStableList[str] = ConcurrentStableList()
    raw, _ = read_value(cur, VIEW_STATE_KEY)
    if raw:
        try:
            state = json.loads(raw)
        except ValueError:
            state = {}
        for name, item in state.items():
            if isinstance(item, dict) and item.get("isHidden"):
                hidden.add(name)

    all_repos: ConcurrentStableList[str] = ConcurrentStableList()
    visible: ConcurrentStableList[int] = ConcurrentStableList()
    raw, _ = read_value(cur, REPOS_KEY)
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        for repo in data.get("all", []) or []:
            all_repos.add(repo)
        for index in data.get("visible", []) or []:
            visible.add(index)

    return ScmState(
        hidden_views=tuple(hidden),
        all_repos=tuple(all_repos),
        visible=tuple(visible),
    )


def describe(state: ScmState) -> None:
    """打印状态明细（仓库逐条标出可见与否）。"""
    hidden = ", ".join(state.hidden_views) if state.hidden_views else "无"
    print(f"      视图 isHidden：{hidden}（此项为正常默认值，不参与判故障）")
    print(f"      仓库总数  ：{len(state.all_repos)}，可见下标：{list(state.visible)}")
    for index, repo in enumerate(state.all_repos):
        mark = "✓" if index in state.visible else "✗"
        print(f"        {mark} [{index}] {repo.split('file://')[-1] or repo}")


def _apply_fix(cur: sqlite3.Cursor) -> ConcurrentStableList[str]:
    """把仓库可见性改回「全部可见」；返回改动说明。

    只改 `scm:view:visibleRepositories`——`workbench.scm.views.state` 的 `isHidden`
    是正常默认值（见 `ScmState.ok`），不予改动，避免无谓的状态写入。
    """
    changed: ConcurrentStableList[str] = ConcurrentStableList()

    raw, as_bytes = read_value(cur, REPOS_KEY)
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        all_repos = data.get("all", []) or []
        if all_repos and len(data.get("visible", []) or []) != len(all_repos):
            data["visible"] = list(range(len(all_repos)))
            write_value(cur, REPOS_KEY, data, as_bytes)
            changed.add(f"恢复 {len(all_repos)} 个仓库可见")

    return changed


def main() -> int:
    profiles = dict(IDE_PROFILES)
    parser = argparse.ArgumentParser(
        description="修复 IDE 源代码管理面板看不到仓库（工作区状态里仓库可见性不全）",
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
        help="工作区目录（默认当前目录），用于定位 workspaceStorage 下的 hash 目录",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="IDE 用户数据目录（默认按 --ide 取 $HOME 下的标准位置）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只查看当前状态，不做修改（无需退出 IDE）",
    )
    args = parser.parse_args()

    profile = profiles[args.ide]
    user_data_dir = Path(args.user_data_dir).expanduser() if args.user_data_dir else Path.home() / profile.user_data_dir
    workspace = Path(args.workspace).expanduser().resolve()
    folder_uri = workspace.as_uri()

    print(f"[目标] {profile.label}")
    print(f"       工作区     ：{workspace}")
    print(f"       用户数据目录：{user_data_dir}")

    if not user_data_dir.is_dir():
        print(f"[失败] 用户数据目录不存在：{user_data_dir}")
        return 1

    db = find_workspace_db(user_data_dir, folder_uri)
    if db is None:
        print(
            f"[失败] 未找到该工作区的 state.vscdb。\n"
            f"       确认「{workspace}」曾用 {profile.label} 打开过，"
            f"或用 --user-data-dir 指定目录。"
        )
        return 1
    print(f"       状态库     ：{db}")

    con = sqlite3.connect(str(db))
    cur = con.cursor()
    before = inspect(cur)

    print("\n[现状]")
    describe(before)

    if args.check:
        con.close()
        if not before.has_repos:
            print("\n[结论] 该工作区未保存过仓库可见性记录（不适用，无需处理）。")
            return 0
        verdict = "面板状态正常。" if before.ok else "仓库可见性不全，可去掉 --check 执行修复。"
        print(f"\n[结论] {verdict}")
        return 0 if before.ok else 2

    if not before.has_repos:
        con.close()
        print("\n[完成] 该工作区未保存过仓库可见性记录（可能是未含 git 仓库，或尚未让 IDE 写过该键），无需处理。")
        return 0

    if ide_running(profile.process_markers):
        print(
            f"\n[中止] 检测到 {profile.label} 仍在运行。\n"
            f"       运行期间改库会被退出时的内存回写覆盖，"
            f"请**完全退出**（含所有窗口）后重跑。"
        )
        con.close()
        return 1

    if before.ok:
        con.close()
        print("\n[完成] 面板状态本就正常，无需修改。")
        return 0

    # 备份（与状态库同目录旁挂 .bak-<时间戳>，便于回滚）
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.name}.bak-{stamp}")
    shutil.copy2(db, backup)
    print(f"\n[1/3] 已备份：{backup}")

    changed = _apply_fix(cur)
    con.commit()

    print("[2/3] 修改完成：")
    for line in changed or ["（无需修改）"]:
        print(f"      - {line}")

    # 3) 回读校验
    after = inspect(cur)
    con.close()
    print("[3/3] 修复后：")
    describe(after)
    if after.ok:
        print(f"\n[完成] 校验通过。重新打开 {profile.label}，源代码管理面板即可看到全部仓库。")
        return 0
    print("\n[警告] 校验未通过，请检查上面的现状输出。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
