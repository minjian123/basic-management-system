#!/usr/bin/env python3
"""依赖重装：还原 → 重新安装（前端 pnpm / 后端 uv）→ 再次外置。

用法（在 bms 仓根执行，Linux / Windows 通用）：
    python3 scripts/tools/deps/重装依赖.py [--frontend-only | --backend-only]
    --frontend-only ：只重装前端（pnpm install），后端环境不动
    --backend-only  ：只重装后端（uv sync），前端不动
    不带参数        ：前后端一起重装（uv sync + pnpm install）
    （Linux 亦可经同名 .sh 瘦包装调用；Windows 亦可经同名 .bat 瘦包装调用）

后端环境外置：uv 项目环境走**链接口径**（`backend/.venv` -> 依赖仓 backend-venv），
不依赖 UV_PROJECT_ENVIRONMENT —— 该变量易随会话/跨仓串环境（2026-10-14 实测：
mdm 目录下 uv run 误装进 bms 共享环境），链接链路每仓自持、不随环境变量漂移。
"""

import os
import shutil
import subprocess
import sys

import deps_common as common

PREFIX = "重装依赖"


def main(argv):
    args = argv[1:]
    known = ("--frontend-only", "--backend-only")
    unknown = [arg for arg in args if arg not in known]
    if unknown:
        sys.stderr.write(f"[{PREFIX}] 未知参数：{unknown[0]}（支持 --frontend-only / --backend-only）\n")
        sys.exit(2)
    frontend_only = "--frontend-only" in args
    backend_only = "--backend-only" in args
    if frontend_only and backend_only:
        sys.stderr.write(f"[{PREFIX}] --frontend-only 与 --backend-only 不能同时使用。\n")
        sys.exit(2)

    root = common.find_repo_root(__file__, PREFIX)
    os.chdir(root)

    # 解析并以环境变量导出：子脚本（还原/外置）读取一致值。
    # 导出的是**依赖仓根**（不含平台子目录）——子脚本会自行再拼平台标签，导出平台目录会叠成 `<根>/windows/windows`。
    deps_dir = common.resolve_deps_dir(root)
    common.ensure_platform_marker(deps_dir, PREFIX)
    os.environ["DEPS_DIR"] = os.path.dirname(deps_dir)
    print(f"[{PREFIX}] 本地依赖仓：{deps_dir}")

    # 依赖命令预检（缺哪个报哪个，避免中途才失败）
    if not frontend_only and not shutil.which("pnpm"):
        sys.stderr.write(f"[{PREFIX}] 未在 PATH 找到 pnpm（见 pnpm 部署使用说明），中止。\n")
        sys.exit(2)
    if not backend_only and not shutil.which("uv"):
        sys.stderr.write(f"[{PREFIX}] 未在 PATH 找到 uv（见 uv 部署使用说明），中止。\n")
        sys.exit(2)

    here = os.path.dirname(os.path.abspath(__file__))

    def run(cmd, cwd, label):
        print(f"[{PREFIX}] {label}")
        code = subprocess.call(cmd, cwd=cwd)
        if code != 0:
            sys.stderr.write(f"[{PREFIX}] {label} 失败（exit={code}），中止。\n")
            sys.exit(1)

    # 1) 先还原（移除外置链接，安装器才能正常重建项目内目录）
    run([sys.executable, os.path.join(here, "还原依赖.py")], root, "还原依赖")

    # 2) 安装
    # 后端一律在 `backend/` 下执行（工程根在 `backend/`，仓根没有 pyproject.toml）：
    # 还原后 `.venv` 已回到 `backend/.venv` 真实目录，uv sync 就地同步该环境。
    if not frontend_only:
        run(["uv", "sync", "--frozen"], os.path.join(root, "backend"), "uv sync --frozen（backend）")
    if not backend_only:
        run(["pnpm", "install", "--frozen-lockfile"], root, "pnpm install --frozen-lockfile")

    # 3) 再次外置
    run([sys.executable, os.path.join(here, "外置依赖.py")], root, "外置依赖")
    print(f"[{PREFIX}] 完成。")
    return 0


if __name__ == "__main__":
    common.configure_stdio()
    sys.exit(main(sys.argv))
