"""reorder-design.py - 设计文档节点编号重排工具

按同目录 order.json 中定义的「阅读顺序」（每个节点的新编号），对设计文档体系做编号重排。
支持两种体系类型（directories[].type）：

  - "single"：单级编号文档（架构设计 / 概要设计 / 布局设计）
      文件形如 {NN}_{体系}_{主题}.html，order.json 的 nodes 定义阅读顺序（新编号）。
  - "proto"：原型设计（两级编号）
      模块文件夹 {NN}_{模块名}/ + 模块内文件 {NN}_{文件名}.html。
      order.json 的 modules 定义模块阅读顺序（新编号），moduleFiles 按模块名配置
      模块内文件阅读顺序（可省略，省略则模块内文件不重排）。

处理内容：
  1. 文件/文件夹重命名：两步法（先统一改为临时名，再改为目标名），规避编号循环导致的覆盖冲突；
  2. 全库引用替换：扫描 scanRoots 目录下全部 *.html，按「旧编号从后往前」的顺序逐个替换
     文件全名 / 文件夹路径段 / 无斜杠文字变体 / 模块内文件名，防止中间态把新名当旧名再次替换；
  3. 总览 01 节点表行排序：按链接文件名的编号对节点表 <tr> 排序（表头保持最前），
     使总览阅读顺序与文件编号一致；
  4. textReplace 附加文本替换（配置中的固定文案）。

幂等：当所有节点已处于目标编号（目标文件存在且无旧编号文件）时，输出"已是最新状态"并跳过。

用法:
    python reorder-design.py --dry-run    预览模式（只打印计划，不执行）
    python reorder-design.py              执行重排
    python reorder-design.py --config path 指定 order.json 路径
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
NUM_RE = re.compile(r"^\d{2}_")


def get_short_subject(name: str, sys_name: str) -> str:
    s = name
    if s.startswith(f"{sys_name}_"):
        s = s[len(sys_name) + 1:]
    if s.startswith("子系统_"):
        s = s[4:]
    return s


def find_old_file(directory: Path, name: str, target_full: Path):
    """找 {NN}_{name}.html 且非目标文件名的旧文件，返回 Path 或 None。"""
    for f in directory.glob(f"*_{name}.html"):
        if NUM_RE.match(f.stem) and f.resolve() != target_full.resolve():
            return f
    return None


def build_file_mappings(dir_cfg: dict, module_name: str, dir_path: Path) -> list:
    """原型模块内文件重排映射（moduleFiles 配置）。"""
    result = []
    for fm in dir_cfg.get("moduleFiles", []):
        if fm.get("name") != module_name:
            continue
        for fnode in fm.get("files", []):
            fname = fnode["name"]
            fto = str(fnode["to"])
            if not dir_path.exists():
                continue
            target = dir_path / f"{fto}_{fname}.html"
            old = find_old_file(dir_path, fname, target)
            if not old:
                if target.exists():
                    continue
                print(f"      新增界面文件（未创建，按目标编号 {fto} 直接创建即可）: {module_name}/{fname}")
                continue
            old_no = old.stem.split("_")[0]
            result.append({
                "OldNo": old_no, "NewNo": fto, "Name": fname,
                "OldFile": old, "OldFull": f"{old_no}_{fname}.html",
                "NewFull": f"{fto}_{fname}.html",
            })
        break
    return result


def sort_overview_tables(html: str) -> str:
    """总览节点表 <tr> 行排序：表头最前，节点按编号升序。"""
    table_pattern = re.compile(r"<table(?P<attrs>[^>]*)>(?P<body>.*?)</table>", re.S)

    def evaluator(m: re.Match) -> str:
        attrs = m.group("attrs")
        body = m.group("body")
        trs = re.findall(r"<tr>.*?</tr>", body, re.S)
        header, nodes, others = [], [], []
        for idx, tr in enumerate(trs):
            if "<th" in tr:
                header.append(tr)
            else:
                nm = re.search(r'href="(?P<no>\d{2})_', tr)
                if nm:
                    nodes.append({"No": int(nm.group("no")), "Html": tr, "Idx": idx})
                else:
                    others.append(tr)
        sorted_rows = []
        for node in sorted(nodes, key=lambda n: (n["No"], n["Idx"])):
            html_row = node["Html"]
            lead = re.match(r"<tr>\s*<td[^>]*>\s*\d{2}\s*</td>", html_row, re.S)
            if lead:
                html_row = f"<tr><td>{node['No']:02d}</td>" + html_row[lead.end():]
            sorted_rows.append(html_row)
        sep = "\n        "
        return f"<table{attrs}>" + sep + sep.join(header + sorted_rows + others) + "\n      </table>"

    return table_pattern.sub(evaluator, html)


def main() -> int:
    parser = argparse.ArgumentParser(description="设计文档节点编号重排工具")
    parser.add_argument("--config", default=str(SCRIPT_DIR / "order.json"), help="order.json 路径（默认脚本同目录）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式：只打印重命名计划与替换规则，不执行任何修改")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    all_pairs = []  # [{"Old", "New", "Key"}]
    overview_files = []

    for dir_cfg in config["directories"]:
        directory = REPO_ROOT / dir_cfg["dir"]
        d_type = dir_cfg.get("type", "single")
        print(f"\n==== {dir_cfg['dir']}（{d_type}） ====")

        if d_type == "single":
            sys_name = dir_cfg["name"]
            mappings = []
            in_place = 0
            for node in dir_cfg["nodes"]:
                name = node["name"]
                to = str(node["to"])
                new_file = directory / f"{to}_{name}.html"
                old = find_old_file(directory, name, new_file)
                if not old:
                    if new_file.exists():
                        in_place += 1
                        continue
                    raise FileNotFoundError(f"未找到节点文件: {name}（{dir_cfg['dir']}）")
                old_no = old.stem.split("_")[0]
                short = node.get("short") or get_short_subject(name, sys_name)
                mappings.append({
                    "OldNo": old_no, "NewNo": to, "Name": name, "OldFile": old,
                    "OldFull": f"{old_no}_{name}.html", "NewFull": f"{to}_{name}.html",
                    "OldShort": f"{old_no}-{short}", "NewShort": f"{to}-{short}",
                })
            dup = {m["NewNo"] for m in mappings}
            if len(dup) != len(mappings):
                raise RuntimeError(f"新编号冲突: {sorted(dup)}（{dir_cfg['dir']}）")
            overview_files.append(directory / f"01_{sys_name}_总览.html")
            if in_place == len(dir_cfg["nodes"]) and not mappings:
                print("  已是最新状态（所有节点编号符合 order.json），跳过")
                continue
            ordered = sorted(mappings, key=lambda m: int(m["OldNo"]), reverse=True)
            print("  重命名计划（旧 → 新）：")
            for m in ordered:
                mark = "" if m["OldNo"] == m["NewNo"] else ""
                print(f"    {m['OldFile'].relative_to(REPO_ROOT)} -> {m['NewNo']}_{m['Name']}.html {mark}")
            if not args.dry_run:
                tmp_files = []
                for m in mappings:
                    tmp = directory / f"{m['OldNo']}_reorder_{m['Name']}.html"
                    m["OldFile"].rename(tmp)
                    tmp_files.append(tmp)
                for m, tmp in zip(mappings, tmp_files):
                    tmp.rename(directory / m["NewFull"])
                print(f"  已重命名 {len(mappings)} 个文件")
            for m in ordered:
                all_pairs.append({"Old": m["OldFull"], "New": m["NewFull"], "Key": int(m["OldNo"])})
                all_pairs.append({"Old": m["OldShort"], "New": m["NewShort"], "Key": int(m["OldNo"])})

        else:  # proto
            module_mappings = []
            file_only_mappings = []
            in_place = 0
            for mod in dir_cfg.get("modules", []):
                mname = mod["name"]
                to = str(mod["to"])
                old_dir = None
                for d in directory.iterdir():
                    if d.is_dir() and NUM_RE.match(d.name) and d.name.endswith(f"_{mname}") and d.name != f"{to}_{mname}":
                        old_dir = d
                        break
                if not old_dir:
                    if (directory / f"{to}_{mname}").exists():
                        in_place += 1
                        fms = build_file_mappings(dir_cfg, mname, directory / f"{to}_{mname}")
                        if fms:
                            file_only_mappings.append({"No": to, "Name": mname,
                                                       "Dir": directory / f"{to}_{mname}", "FileMappings": fms})
                        continue
                    print(f"  新增模块（文件夹未创建，按目标编号 {to} 直接创建即可）: {mname}")
                    continue
                old_no = old_dir.name.split("_")[0]
                module_mappings.append({
                    "OldNo": old_no, "NewNo": to, "Name": mname, "OldDir": old_dir,
                    "OldSeg": f"{old_no}_{mname}/", "NewSeg": f"{to}_{mname}/",
                    "OldTxt": f"{old_no}_{mname}", "NewTxt": f"{to}_{mname}",
                    "FileMappings": build_file_mappings(dir_cfg, mname, old_dir),
                })
            dup = {m["NewNo"] for m in module_mappings}
            if len(dup) != len(module_mappings):
                raise RuntimeError(f"模块新编号冲突: {sorted(dup)}（{dir_cfg['dir']}）")
            overview_files.append(directory / "01_原型设计_总览.html")

            need_work = len(module_mappings) + len(file_only_mappings)
            if in_place == len(dir_cfg.get("modules", [])) and need_work == 0:
                print("  已是最新状态（所有模块编号符合 order.json），跳过")
                continue
            ordered_mods = sorted(module_mappings, key=lambda m: int(m["OldNo"]), reverse=True)

            print("  重命名计划：")
            for m in ordered_mods:
                print(f"    模块文件夹: {m['OldDir'].relative_to(REPO_ROOT)} -> {m['NewNo']}_{m['Name']}/")
                for fm in m["FileMappings"]:
                    print(f"      模块内文件: {fm['OldFull']} -> {fm['NewFull']}")
            for m in file_only_mappings:
                print(f"    模块内文件（文件夹不变）: {m['Dir'].relative_to(REPO_ROOT)}/")
                for fm in m["FileMappings"]:
                    print(f"      {fm['OldFull']} -> {fm['NewFull']}")

            if not args.dry_run:
                # 第一步：文件夹变化模块的文件夹与模块内文件改临时名
                for m in module_mappings:
                    tmp_dir = directory / f"{m['OldNo']}_reorder_{m['Name']}"
                    m["OldDir"].rename(tmp_dir)
                    m["TmpDir"] = tmp_dir
                    for fm in m["FileMappings"]:
                        fm["OldFile"] = tmp_dir / fm["OldFile"].name
                for m in module_mappings:
                    for fm in m["FileMappings"]:
                        tmp_name = f"{fm['OldNo']}_reorder_{fm['Name']}.html"
                        fm["OldFile"].rename(m["TmpDir"] / tmp_name)
                        fm["TmpFile"] = m["TmpDir"] / tmp_name
                # 仅文件重排模块：文件改临时名
                for m in file_only_mappings:
                    for fm in m["FileMappings"]:
                        tmp_name = f"{fm['OldNo']}_reorder_{fm['Name']}.html"
                        fm["OldFile"].rename(m["Dir"] / tmp_name)
                        fm["TmpFile"] = m["Dir"] / tmp_name
                # 第二步：临时名 → 目标名
                for m in module_mappings:
                    target_dir = directory / f"{m['NewNo']}_{m['Name']}"
                    m["TmpDir"].rename(target_dir)
                    for fm in m["FileMappings"]:
                        fm["TmpFile"] = target_dir / fm["TmpFile"].name
                        fm["TmpFile"].rename(target_dir / fm["NewFull"])
                for m in file_only_mappings:
                    for fm in m["FileMappings"]:
                        fm["TmpFile"].rename(m["Dir"] / fm["NewFull"])
                print(f"  已重命名 {len(module_mappings)} 个模块文件夹 + {len(file_only_mappings)} 个模块内文件")

            for m in ordered_mods:
                key = int(m["OldNo"])
                all_pairs.append({"Old": m["OldSeg"], "New": m["NewSeg"], "Key": key})
                all_pairs.append({"Old": m["OldTxt"], "New": m["NewTxt"], "Key": key})
                for fm in m["FileMappings"]:
                    all_pairs.append({"Old": fm["OldFull"], "New": fm["NewFull"], "Key": key})
            for m in file_only_mappings:
                key = int(m["No"])
                for fm in m["FileMappings"]:
                    all_pairs.append({"Old": fm["OldFull"], "New": fm["NewFull"], "Key": key})

    # ---------- 引用替换 ----------
    scan_files = []
    for root in config.get("scanRoots", []):
        root_path = REPO_ROOT / root
        if root_path.exists():
            scan_files.extend(root_path.rglob("*.html"))

    ordered_pairs = []
    # 替换顺序：按旧编号 Key 从后往前（降序），同 Key 保持添加顺序
    seq = {id(p): i for i, p in enumerate(all_pairs)}
    ordered_pairs = sorted(all_pairs, key=lambda p: (-p["Key"], seq[id(p)]))

    if not args.dry_run:
        updated = 0
        for file in scan_files:
            content = file.read_text(encoding="utf-8")
            orig = content
            for p in ordered_pairs:
                content = content.replace(p["Old"], p["New"])
            for t in config.get("textReplace", []):
                content = content.replace(t["from"], t["to"])
            if content != orig:
                file.write_text(content, encoding="utf-8")
                updated += 1
                print(f"  更新引用: {file.relative_to(REPO_ROOT)}")
        print(f"\n引用替换完成：更新 {updated} / {len(scan_files)} 个文件")
    else:
        print(f"\n[DryRun] 将扫描 {len(scan_files)} 个 html 文件进行引用替换：{len(ordered_pairs)} 对全名/路径段替换（按旧编号从后往前）")
        for t in config.get("textReplace", []):
            print(f"  附加文本: \"{t['from']}\" -> \"{t['to']}\"")

    # ---------- 总览 01 节点表行排序 ----------
    for ov in overview_files:
        if not ov.exists():
            print(f"警告: 未找到总览文件: {ov}")
            continue
        content = ov.read_text(encoding="utf-8")
        sorted_html = sort_overview_tables(content)
        if sorted_html != content:
            if args.dry_run:
                print(f"  [DryRun] 总览表将排序: {ov.relative_to(REPO_ROOT)}")
            else:
                ov.write_text(sorted_html, encoding="utf-8")
                print(f"  总览表已排序: {ov.relative_to(REPO_ROOT)}")

    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())