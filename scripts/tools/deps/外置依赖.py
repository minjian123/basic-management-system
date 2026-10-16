#!/usr/bin/env python3
"""依赖外置：把项目内依赖目录整体搬移至本地依赖仓，原位置留目录链接。

效果：磁盘占用归零、内容不出项目（检索/扫描工具默认不跟随链接即扫不到）。
适用对象：pnpm workspace 的 node_modules 目录 + 后端 `.venv`（backend/.venv）。

用法（在 bms 仓根执行，Linux / Windows 通用）：
    python3 scripts/tools/deps/外置依赖.py [--dry-run]
    （Linux 亦可经同名 .sh 瘦包装调用；Windows 亦可经同名 .bat 瘦包装调用）

本地依赖仓目录（本地资源信息，不入公开文档）：
  1) 环境变量 DEPS_DIR；
  2) bms/deploy/.env 中的 DEPS_DIR=；
  3) 缺省 $HOME/dev-deps/bms。

平台口径：Linux 建绝对路径符号链接；Windows 建 junction（mklink /J）。
配套：还原依赖.py（搬回原位）、重装依赖.py（还原→安装→再外置）。
"""

import os
import sys

import deps_common as common

PREFIX = "外置依赖"


def main(argv):
    dry_run = "--dry-run" in argv[1:]

    root = common.find_repo_root(__file__, PREFIX)
    os.chdir(root)

    deps_dir = common.resolve_deps_dir(root)
    common.validate_layout(root, deps_dir, PREFIX)
    common.warn_cross_volume(root, deps_dir)
    print(f"[{PREFIX}] 本地依赖仓：{deps_dir}")
    print(f"[{PREFIX}] 项目根：{root}")

    # ---- node_modules 外置 ----
    # 先收集全部候选再统一搬移（遍历中搬走目录会中断遍历，与 shell 版同口径）。
    count = 0
    root_name = os.path.basename(root)
    for src in common.find_node_modules_dirs(root):
        rel = os.path.relpath(src, root)
        # 与仓库同名的嵌套目录＝路径前缀重复误建出的幽灵目录，跳过（防再次搬移污染依赖仓）
        if rel.split(os.sep, 1)[0] == root_name:
            sys.stderr.write(f"[跳过] {rel}（位于与仓库同名的嵌套目录，疑似前缀重复误建）\n")
            continue
        dest = os.path.join(deps_dir, rel)
        print(f"[外置] {rel}")
        count += 1
        if dry_run:
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.lexists(dest):
            common.remove_path_safe(dest)
        common.move_dir(src, dest)
        common.create_link(src, dest)
    print(f"[外置] 完成：共 {count} 个依赖目录。")

    # ---- 修复 workspace 包链接 ----
    # pnpm 的 workspace 包链接（如 node_modules/@bms/core）是指向项目源码的相对链接；
    # 依赖目录整体搬到依赖仓后该相对路径改以依赖仓为基准解析而断裂，依赖它的包随之报
    # 「Cannot find module '@bms/core'」，本地类型检查 / 测试失败。
    # 此处把这类断链重写为指向项目源码的绝对链接：外置收益不变，本地门禁与 CI 口径一致。
    # 幂等：已指向项目内的链接解析后不以依赖仓开头，天然跳过。
    deps_norm = common.norm(deps_dir)
    for link in common.find_reparse_points(deps_dir):
        target = common.link_target(link)
        if not target:
            continue
        if common.norm(target) == deps_norm:
            continue
        if not common.is_within(target, deps_dir):
            continue
        # 完整包目录（含 package.json）或存在的文件类链接 → 正常，跳过；其余视为工作区链接候选
        if os.path.isfile(os.path.join(target, "package.json")):
            continue
        if os.path.exists(target) and not os.path.isdir(target):
            continue
        rel_fix = os.path.relpath(target, deps_dir)
        src = os.path.join(root, rel_fix)
        if not os.path.exists(src):
            continue
        print(f"[修复] 工作区链接 {os.path.relpath(link, deps_dir)} -> {src}")
        if dry_run:
            continue
        common.remove_link(link)
        common.create_link(link, src)

    # ---- 后端 .venv 外置 ----
    # 与 node_modules 同口径：真实目录整体搬到依赖仓，原位留链接。之所以能这么做，是因为
    # 基座工程根定位（`bms_core.core.paths.resolve_backend_root`）**不穿透链接**——外置态下
    # 包体虽在依赖仓，仍能经 `backend/.venv/...` 这一字面层级上溯到仓库内工程根。
    # 依赖仓已有环境时以依赖仓为准：仓内若残留真实目录（历史上非交互式 uv 调用所建）即删除，
    # 避免两份环境并存混淆（两份内容可以不一致，误用会得到难以排查的行为差异）。
    venv_live = os.path.join(root, "backend", ".venv")
    venv_store = os.path.join(deps_dir, "backend-venv")
    if common.is_link(venv_live):
        print("[跳过] backend/.venv 是链接（已外置）")
    elif os.path.isdir(venv_store):
        if os.path.lexists(venv_live):
            print("[外置] backend/.venv：依赖仓已有环境，删除仓内残留目录（以依赖仓为准）")
            count += 1
            if not dry_run:
                common.remove_path_safe(venv_live)
        else:
            print("[外置] backend/.venv：采用依赖仓现有环境（原位建链接）")
        if dry_run:
            print(f"[dry-run] 建链接 {venv_live} -> {venv_store}")
        else:
            common.create_link(venv_live, venv_store)
    elif os.path.isdir(venv_live):
        print("[外置] backend/.venv")
        count += 1
        if not dry_run:
            os.makedirs(deps_dir, exist_ok=True)
            common.move_dir(venv_live, venv_store)
            common.create_link(venv_live, venv_store)
    else:
        print("[跳过] backend/.venv 不存在（先 uv sync 生成，或本仓未启用后端外置）")

    print("[外置] 查看本地依赖仓体积： du -sh <依赖仓>（Windows 可看文件夹属性）")
    print("[外置] 确认项目内为链接： ls -la <包>/node_modules（Windows 为 junction）")
    return 0


if __name__ == "__main__":
    common.configure_stdio()
    sys.exit(main(sys.argv))
