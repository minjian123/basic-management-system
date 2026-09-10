#!/usr/bin/env python3
"""基座同步工具：bms 仓库（权威源）→ 产品仓库。

按《基座文档清单》定义的基座目录，比较 bms 与产品仓库的基座文件差异，
输出变更明细，人工确认后覆盖。不引入 git submodule（清单 + 脚本 + 人工确认）。

用法:
  base-sync.py list                        列出 bms 基座文件清单
  base-sync.py sync --target <产品仓库> [--dry-run] [--scope update|new|all] [--dir <子目录>] [--apply]

默认 --dry-run（只输出差异）；加 --apply 才实际写入。
"""
import argparse
import difflib
import hashlib
import os
import sys

BASE_DIRS = [
    "文档/规范",
    "文档/资源",
    "文档/资料/AI",
    "文档/资料/工具",
    "文档/资料/开发服务器",
    "文档/资料/开发机",
    "文档/资料/知识档案",
]
# 凭据模板类（各仓库自带副本、内容各异），不参与同步
EXCLUDED = {"文档/用户文档"}


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def scan(src_root):
    files = {}
    for d in BASE_DIRS:
        base = os.path.join(src_root, d)
        if not os.path.isdir(base):
            continue
        for dp, _, fs in os.walk(base):
            for f in fs:
                rel = os.path.normpath(os.path.relpath(os.path.join(dp, f), src_root))
                files[rel] = os.path.join(src_root, rel)
    return files


def diff_lines(a_path, b_path):
    a = open(a_path, encoding="utf-8", errors="ignore").readlines()
    b = open(b_path, encoding="utf-8", errors="ignore").readlines()
    n = 0
    for line in difflib.unified_diff(a, b, lineterm=""):
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            n += 1
    return n


def diff(src_root, tgt_root):
    src = scan(src_root)
    updates, news, same = [], [], 0
    for rel, ab in sorted(src.items()):
        tp = os.path.join(tgt_root, rel)
        if not os.path.exists(tp):
            news.append(rel)
        elif md5(ab) != md5(tp):
            updates.append(rel)
        else:
            same += 1
    tgt = set()
    for d in BASE_DIRS:
        base = os.path.join(tgt_root, d)
        if os.path.isdir(base):
            for dp, _, fs in os.walk(base):
                for f in fs:
                    tgt.add(os.path.normpath(os.path.relpath(os.path.join(dp, f), tgt_root)))
    prod_extra = sorted(tgt - set(src))
    return src, updates, news, same, prod_extra


def show(src, updates, news, same, prod_extra, tgt_root, scope):
    print(f"基座文件: {len(src)}  |  一致 {same}  差异 {len(updates)}  产品缺失 {len(news)}  产品独有 {len(prod_extra)}")
    if scope in ("update", "all") and updates:
        print(f"\n== 更新（产品侧有改动，需覆盖，{len(updates)}） ==")
        for rel in updates:
            print(f"  ~ {rel}  ({diff_lines(src[rel], os.path.join(tgt_root, rel))} 行)")
    if scope in ("new", "all") and news:
        print(f"\n== 新增（产品侧缺失，{len(news)}） ==")
        for rel in news:
            print(f"  + {rel}")
    if prod_extra:
        print(f"\n== 产品独有（不受影响，不删不覆盖，{len(prod_extra)}） ==")
        for rel in prod_extra:
            print(f"  · {rel}")


def apply(src, updates, news, tgt_root, scope):
    targets = []
    if scope in ("update", "all"):
        targets += updates
    if scope in ("new", "all"):
        targets += news
    for rel in targets:
        sp = src[rel]
        tp = os.path.join(tgt_root, rel)
        os.makedirs(os.path.dirname(tp), exist_ok=True)
        shutil_copy(sp, tp)
    print(f"已写入 {len(targets)} 个文件")


def shutil_copy(sp, tp):
    import shutil
    shutil.copy2(sp, tp)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ls = sub.add_parser("list", help="输出基座文件清单")
    p_ls.add_argument("--src", default=".", help="bms 仓库根目录（默认当前目录）")
    p_sy = sub.add_parser("sync", help="比较并同步基座到产品仓库")
    p_sy.add_argument("--target", required=True, help="产品仓库根目录")
    p_sy.add_argument("--src", default=".", help="bms 仓库根目录（默认当前目录）")
    p_sy.add_argument("--scope", choices=["update", "new", "all"], default="all", help="同步范围（默认 all）")
    p_sy.add_argument("--dir", help="仅同步该子目录（相对文档/ 的路径，如 规范）")
    p_sy.add_argument("--apply", action="store_true", help="实际写入（默认仅 dry-run 输出差异）")
    args = ap.parse_args()

    if args.cmd == "list":
        for rel in sorted(scan(args.src)):
            print(rel)
        return

    src_root = os.path.abspath(args.src)
    tgt_root = os.path.abspath(args.target)
    if not os.path.isdir(os.path.join(src_root, "文档")):
        sys.exit("源目录下找不到 文档/，请在 bms 仓库根目录运行")
    if not os.path.isdir(tgt_root):
        sys.exit(f"目标目录不存在: {tgt_root}")

    src, updates, news, same, prod_extra = diff(src_root, tgt_root)
    if args.dir:
        d = os.path.normpath(args.dir)
        updates = [r for r in updates if r.startswith("文档/" + d)]
        news = [r for r in news if r.startswith("文档/" + d)]

    show(src, updates, news, same, prod_extra, tgt_root, args.scope)

    if args.apply:
        apply(src, updates, news, tgt_root, args.scope)
    else:
        print("\n[dry-run] 如需写入请加 --apply")


if __name__ == "__main__":
    main()