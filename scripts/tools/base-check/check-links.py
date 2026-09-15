#!/usr/bin/env python3
"""基座文档链接自洽校验（本地手工跑，不挂 CI）。

**为什么独立出来**：链接校验对文档写作约束太强——指向未建档文件、其他仓库软链内
路径等的链接都会判断链，逼着文档刻意少写导航链接，损害阅读体验。因此从
`check-base.py`（CI `base-integrity` 强制项）中拆出，**只在需要时手工运行**：
写完一批文档、重构目录、或想把某批链接收进 CI 前核对一次。

校验内容：全库 `bms文档/` 相对链接自洽——断链 0、失效锚点 0
（跳过行内代码与外部链接；gitignore 的本地文档如 `用户文档/` 不参与）。

用法::

    python3 scripts/tools/base-check/check-links.py            # bms 仓库根运行
    python3 scripts/tools/base-check/check-links.py <其他根>     # 指定根目录

退出码：有问题 1，通过 0。
"""
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
# 本地凭据文档不入库（gitignore）：存在与否不参与链接校验
LOCAL_ONLY = ("bms文档/用户文档/",)
LINK_RE = re.compile(r'\]\(([^)\s]+)\)')
CODE_RE = re.compile(r'`[^`]*`')

problems = []


def strip_code(line):
    return CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def check_links():
    n_file = n_anchor = 0
    for dp, dns, fs in os.walk(os.path.join(ROOT, "bms文档")):
        dns[:] = [d for d in dns if d not in {".git"}]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT)
            for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                for m in LINK_RE.finditer(strip_code(line)):
                    t = m.group(1).strip()
                    if t.startswith(("http", "mailto", "data:")) or not t:
                        continue
                    path, _, anc = t.partition("#")
                    path = path.lstrip("?")
                    if not path:
                        continue
                    tp = os.path.normpath(os.path.join(dp, path))
                    trel = os.path.relpath(tp, ROOT)
                    if trel.startswith(LOCAL_ONLY):
                        continue  # 本地凭据文档不入库（gitignore）：存在与否不参与链接校验
                    if not os.path.exists(tp):
                        problems.append(f"[断链] {rel}:{i} -> {t}")
                        n_file += 1
                        continue
                    if anc and tp.endswith(".md"):
                        if f'id="{anc}"' not in open(tp, encoding="utf-8", errors="ignore").read():
                            problems.append(f"[失效锚点] {rel}:{i} -> {t}")
                            n_anchor += 1
    print(f"链接自洽：断链 {n_file} 处，失效锚点 {n_anchor} 处（扫描根：{ROOT}）")


def main():
    check_links()
    if problems:
        print(f"\n[check-links] 不通过：{len(problems)} 项")
        for p in problems[:50]:
            print("  " + p)
        if len(problems) > 50:
            print(f"  ... 其余 {len(problems) - 50} 项")
        sys.exit(1)
    print("\n[check-links] 通过：全库相对链接无断链、无失效锚点。")


if __name__ == "__main__":
    main()
