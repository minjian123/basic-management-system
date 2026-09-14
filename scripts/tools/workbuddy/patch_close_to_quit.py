"""重打 WorkBuddy「关窗即退出」补丁（Linux）。

背景：WorkBuddy 在 Windows/Linux 上硬编码「关窗进托盘、后台常驻」，关窗后进程
      仍在跑。详见 bms《WorkBuddy部署使用说明》「关窗即退出改造」节。

做法：把 app.asar 中托盘初始化的
      `if (!isDarwin) this.trayActive = true;`
      等长替换为
      `if (false    ) this.trayActive = true;`
      令 Linux 关窗时不走隐藏分支（等长字节替换，不改文件长度，无需重算 asar
      头部偏移）。

用法:
    python3 patch_close_to_quit.py            # 一键重打（需退出应用；非 root 自动 sudo 提权）
    python3 patch_close_to_quit.py status     # 查看状态（补丁 / 备份 / 是否在运行）
    python3 patch_close_to_quit.py restore    # 用 app.asar.bak 还原官方默认行为
    python3 patch_close_to_quit.py apply --asar /path/to/app.asar

升级说明：`.deb` 覆盖安装或应用自动更新会替换 app.asar、使补丁丢失，重新执行
          `apply`（或直接跑本脚本）即可；改动前会自动备份为 app.asar.bak。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_ASAR = Path("/opt/WorkBuddy/resources/app.asar")
TARGET = b"if (!isDarwin) this.trayActive = true;"
REPLACED = b"if (false    ) this.trayActive = true;"  # 与 TARGET 等长
ENV_ELEVATED = "_WORKBUDDY_PATCH_ELEVATED"


def app_running() -> bool:
    """WorkBuddy 主进程是否在运行（按进程名精确匹配，避免误伤其它命令）。"""
    return subprocess.call(["pgrep", "-x", "workbuddy"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def state_of(data: bytes) -> str:
    has_target = data.count(TARGET)
    has_repl = data.count(REPLACED)
    if has_repl and not has_target:
        return "patched"
    if has_target and not has_repl:
        return "original"
    if has_target and has_repl:
        return "mixed"
    return "unknown"


def do_status(asar: Path) -> int:
    print(f"asar 路径 : {asar}")
    print(f"备份路径 : {asar.with_name(asar.name + '.bak')}")
    print(f"应用在跑 : {'是' if app_running() else '否'}")
    if not asar.exists():
        print("[状态] asar 不存在")
        return 1
    data = asar.read_bytes()
    st = state_of(data)
    label = {"patched": "已打补丁（关窗即退出）",
             "original": "官方原始（关窗进托盘）",
             "mixed": "异常：目标串与补丁串同时存在",
             "unknown": "异常：两条特征串都未找到（版本可能已变）"}[st]
    print(f"补丁状态 : {label}（大小 {len(data)} 字节）")
    return 0 if st in ("patched", "original") else 1


def do_apply(asar: Path) -> int:
    if app_running():
        print("[中止] 检测到 WorkBuddy 正在运行，请先完全退出（关窗即退出后可直接关窗）。")
        return 1
    if not asar.exists():
        print(f"[失败] 未找到 {asar}")
        return 1

    data = asar.read_bytes()
    st = state_of(data)
    if st == "patched":
        print("[跳过] 已是补丁状态，无需重打。")
        return 0
    if st != "original":
        print(f"[失败] asar 特征异常（state={st}），未改动。可能版本已变，请重新定位补丁点。")
        return 1

    backup = asar.with_name(asar.name + ".bak")
    if backup.exists():
        print(f"[备份] 已存在 {backup}，保留不动。")
    else:
        shutil.copy2(asar, backup)
        print(f"[备份] 已创建 {backup}")

    new = data.replace(TARGET, REPLACED)
    if len(new) != len(data):
        print("[失败] 替换后长度变化，中止。")
        return 1
    try:
        with open(asar, "r+b") as f:
            f.write(new)
    except PermissionError:
        print("[失败] 无写入权限，请以 root 运行（脚本会自动 sudo 提权）。")
        return 1

    diff = sum(1 for a, b in zip(new, data) if a != b)
    print(f"[完成] 补丁已写入，差异 {diff} 字节；启动应用后关窗即退出。")
    print("       验证：grep 'System tray initialized' ~/.workbuddy/logs/main.log | tail -1  →  trayActive=false")
    return 0


def do_restore(asar: Path) -> int:
    if app_running():
        print("[中止] 检测到 WorkBuddy 正在运行，请先完全退出。")
        return 1
    backup = asar.with_name(asar.name + ".bak")
    if not backup.exists():
        print(f"[失败] 找不到备份 {backup}，无法还原。")
        return 1
    try:
        shutil.copy2(backup, asar)
    except PermissionError:
        print("[失败] 无写入权限，请以 root 运行（脚本会自动 sudo 提权）。")
        return 1
    st = state_of(asar.read_bytes())
    print(f"[完成] 已用备份还原（state={st}），重启应用后恢复「关窗进托盘」。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="重打 WorkBuddy「关窗即退出」补丁")
    parser.add_argument("action", nargs="?", default="apply",
                        choices=["apply", "status", "restore"], help="默认 apply")
    parser.add_argument("--asar", type=Path, default=DEFAULT_ASAR, help="app.asar 路径")
    args = parser.parse_args()

    if args.action in ("apply", "restore") and os.geteuid() != 0 \
            and os.environ.get(ENV_ELEVATED) != "1":
        os.environ[ENV_ELEVATED] = "1"
        print("[提权] 需要 root 修改 /opt/WorkBuddy，改用 sudo 重新执行 ...", flush=True)
        return subprocess.call(["sudo", sys.executable, os.path.abspath(__file__),
                                *sys.argv[1:]])

    if args.action == "status":
        return do_status(args.asar)
    if args.action == "apply":
        return do_apply(args.asar)
    return do_restore(args.asar)


if __name__ == "__main__":
    sys.exit(main())
