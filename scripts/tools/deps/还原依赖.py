#!/usr/bin/env python3
"""依赖还原：删除项目内的外置链接，把本地依赖仓中的依赖目录搬回项目原位。

配套用场景：执行 pnpm install / uv sync 等安装动作前的必要前置（安装器会重建项目内目录，
面对链接形态会误判跳过或行为不一致）。

用法（在 bms 仓根执行，Linux / Windows 通用）：
    python3 scripts/tools/deps/还原依赖.py [--dry-run]
    （Linux 亦可经同名 .sh 瘦包装调用；Windows 亦可经同名 .bat 瘦包装调用）
"""

import os
import sys

import deps_common as common

PREFIX = "还原依赖"


def main(argv):
    dry_run = "--dry-run" in argv[1:]

    root = common.find_repo_root(__file__, PREFIX)
    os.chdir(root)

    deps_dir = common.resolve_deps_dir(root)
    common.ensure_platform_marker(deps_dir, PREFIX)
    print(f"[{PREFIX}] 本地依赖仓：{deps_dir}")

    count = 0
    if os.path.isdir(deps_dir):
        # 先收集全部清单再统一搬移（与 shell 版同口径）：遍历中搬走目录会中断遍历。
        for src in common.find_node_modules_dirs(deps_dir):
            rel = os.path.relpath(src, deps_dir)
            dst = os.path.join(root, rel)
            # 仅当原位是「指向依赖仓此目录的链接」才还原（链接目标相等性校验，防错位误搬）
            if not common.is_link(dst):
                continue
            target = common.link_target(dst)
            if not target or common.norm(target) != common.norm(src):
                continue
            # 项目内父目录必须存在（不存在即路径错位，搬回会失败或落到意外位置）
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent):
                sys.stderr.write(f"[跳过] {rel}：项目内父目录不存在，疑似路径错位\n")
                continue
            print(f"[还原] {rel}")
            count += 1
            if dry_run:
                continue
            common.remove_link(dst)
            # 目录整体搬回（同分区 rename，保留内部链接结构）
            common.move_dir(src, dst)

        # ---- 后端 .venv 还原 ----
        # 与 node_modules 同口径：删原位链接，把依赖仓环境搬回 `backend/.venv`。
        # 依赖仓无对应环境时不动（该仓未启用后端外置）。
        venv_link = os.path.join(root, "backend", ".venv")
        venv_store = os.path.join(deps_dir, "backend-venv")
        if common.is_link(venv_link) and os.path.isdir(venv_store):
            if common.reject_foreign_venv(venv_store, PREFIX):
                print("[跳过] backend/.venv：依赖仓环境由另一平台创建，本平台不可用（见上方提示）")
            else:
                print("[还原] backend/.venv")
                count += 1
                if not dry_run:
                    common.remove_link(venv_link)
                    common.move_dir(venv_store, venv_link)

    print(f"[{PREFIX}] 完成：共 {count} 个依赖目录已搬回。")
    return 0


if __name__ == "__main__":
    common.configure_stdio()
    sys.exit(main(sys.argv))
