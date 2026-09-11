#!/usr/bin/env python3
"""基座完整性校验（bms 权威源侧，CI 与本地运行）。

校验五项：
  1. 全库 `bms文档/` 相对链接自洽：断链 0、失效锚点 0（跳过行内代码与外部链接）；
  2. 基座文件不含跨层相对链接（指向平台专属 `bms文档/规划`、`bms文档/项目`、`bms文档/设计`）；
  3. 基座文件不含项目专属措辞残留（`BMS 项目`、`在 BMS`、`本项目项目`）；
  4. 《基座文档清单》与磁盘一致：清单登记的基座文件均存在，且数量与扫描结果一致；
  5. 跨文档引用不得只写编号：指向另一份文档的引用应写章节名（编号随目标文档重排会静默错指）；
     同文档内引用不受限（同一文件内编号与标题同步修改）。

任一项不通过则退出码 1。工作区模型下基座不再向产品仓库复制/同步，产品侧以符号链接引用基座。
"""
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
MANIFEST = "bms文档/基座文档清单.md"
BASE_DIRS = [
    "bms文档/规范", "bms文档/资源", "bms文档/资料/AI", "bms文档/资料/工具",
    "bms文档/资料/开发服务器", "bms文档/资料/开发机", "bms文档/资料/知识档案",
]
# ② 各仓库自带副本：登记但不参与校验（已 gitignore，工作区中可能不存在）
LOCAL_ONLY = ("bms文档/用户文档/",)
CROSS_LAYER = ("bms文档/规划/", "bms文档/项目/", "bms文档/设计/", "bms文档/需求/", "bms文档/任务/")
BAD_WORDING = ("BMS 项目", "在 BMS", "本项目项目")
LINK_RE = re.compile(r'\]\(([^)\s]+)\)')
CODE_RE = re.compile(r'`[^`]*`')

problems = []


def strip_code(line):
    return CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def check_links():
    n_file = n_anchor = 0
    for dp, dns, fs in os.walk(os.path.join(ROOT, "bms文档")):
        dns[:] = [d for d in dns if d not in {".git", "graphify-out"}]
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
    print(f"1. 链接自洽：断链 {n_file} 处，失效锚点 {n_anchor} 处")


def check_cross_layer():
    n = 0
    for d in BASE_DIRS:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(dp, f)
                for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                    for m in LINK_RE.finditer(strip_code(line)):
                        t = m.group(1).strip().lstrip("?")
                        if t.startswith(("http", "mailto")) or not t.split("#")[0].endswith((".md", ".html")):
                            continue
                        ab = os.path.relpath(os.path.normpath(os.path.join(dp, t.split("#")[0])), ROOT)
                        if ab.replace(os.sep, "/").startswith(CROSS_LAYER) or ab.count(os.sep) == 0 and ab.startswith("bms文档/"):
                            if any(ab.replace(os.sep, "/") == b.rstrip("/") for b in CROSS_LAYER) or \
                               ab.replace(os.sep, "/").startswith(CROSS_LAYER):
                                problems.append(f"[跨层引用] {os.path.relpath(p, ROOT)}:{i} -> {t}")
                                n += 1
    print(f"2. 基座跨层引用：{n} 处（应为 0，跨层一律写「平台《文档名》」）")


def check_wording():
    n = 0
    for d in BASE_DIRS:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(dp, f)
                for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                    for w in BAD_WORDING:
                        if w in line:
                            problems.append(f"[措辞残留] {os.path.relpath(p, ROOT)}:{i} 含「{w}」")
                            n += 1
    print(f"3. 项目专属措辞残留：{n} 处（应为 0）")


def manifest_files():
    txt = open(os.path.join(ROOT, MANIFEST), encoding="utf-8").read()
    m = re.search(r'```text\n(.*?)```', txt, re.S)
    if not m:
        return []
    stack, out = [], []
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        mm = re.match(r'^([│\s]*)(?:├──|└──)\s+(.+?)\s*$', line)
        if not mm:
            continue
        depth = len(mm.group(1)) // 4
        name = mm.group(2).split("#")[0].strip()
        stack = stack[:depth]
        if name.endswith("/"):
            stack.append(name.rstrip("/"))
        else:
            out.append("bms文档/" + "/".join(stack + [name]))
    return out


def check_manifest():
    entries = [e for e in manifest_files() if not e.startswith(LOCAL_ONLY)]
    missing = [e for e in entries if not os.path.exists(os.path.join(ROOT, e))]
    disk = 0
    for d in BASE_DIRS:
        for _, _, fs in os.walk(os.path.join(ROOT, d)):
            disk += len(fs)
    for e in missing:
        problems.append(f"[清单缺文件] {MANIFEST} 登记但磁盘不存在：{e}")
    if disk != len(entries):
        problems.append(f"[清单数量不符] 清单登记 {len(entries)} 个，磁盘 {disk} 个（新增/删除基座文件后须同步更新第 2 节清单）")
    print(f"4. 清单一致：登记 {len(entries)} 个，磁盘 {disk} 个，缺失 {len(missing)} 个")


def check_section_refs():
    """跨文档引用若只写编号（第 N 节 / N.M 节 / N 章）即报警。"""
    # 必须有“节/章”字样才判定，避免命中「《X》2026 版」这类非引用文本
    REF_RE = re.compile(r'《(.+?)》[）)，、\s]*(?:第\s*\d+(?:\.\d+)?\s*[章节]|\d+(?:\.\d+)?\s*[章节])')
    n = 0
    for dp, dns, fs in os.walk(os.path.join(ROOT, "bms文档")):
        dns[:] = [d for d in dns if d not in {".git", "graphify-out"}]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT)
            stem = f[:-3]
            for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                for m in REF_RE.finditer(strip_code(line)):
                    raw = m.group(1)
                    name = raw.split("]")[0].lstrip("[") if "]" in raw else raw
                    name = name.strip()
                    # 同文档内自引不受限（编号与标题在同一文件内同步修改）
                    if name == stem or name.replace(" ", "") == stem or stem in name or name in stem:
                        continue
                    problems.append(f"[编号引用] {rel}:{i} -> {m.group(0)[:60]}（跨文档引用请写章节名）")
                    n += 1
    print(f"5. 跨文档编号引用：{n} 处（应为 0，跨文档引用优先写章节名）")


def main():
    check_links()
    check_cross_layer()
    check_wording()
    check_manifest()
    check_section_refs()
    if problems:
        print(f"\n[base-integrity] 不通过：{len(problems)} 项")
        for p in problems[:50]:
            print("  " + p)
        if len(problems) > 50:
            print(f"  ... 其余 {len(problems) - 50} 项")
        sys.exit(1)
    print("\n[base-integrity] 通过：基座链接自洽、无跨层引用、无措辞残留、清单与磁盘一致、跨文档引用均写章节名。")


if __name__ == "__main__":
    main()
