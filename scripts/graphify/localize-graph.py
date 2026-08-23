"""localize-graph.py - graphify 图谱产物一键收尾脚本

用法：graphify update . 重建图谱后运行本脚本，完成两件事：
  1. 汉化 graph.html 界面文案（英文 -> 中文，幂等可反复执行）
  2. 生成中文界面的架构流程图 graphify-out/CALLFLOW.html（graphify export callflow-html --lang zh-CN）

  python scripts/graphify/localize-graph.py
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="graphify 图谱产物汉化与架构图生成")
    parser.add_argument("--graph-html", default="graphify-out/graph.html", help="graph.html 路径")
    parser.add_argument("--callflow-output", default="graphify-out/CALLFLOW.html", help="CALLFLOW.html 输出路径")
    parser.add_argument("--skip-callflow", action="store_true", help="跳过架构图生成")
    args = parser.parse_args()

    graph_html = Path(args.graph_html)
    if not graph_html.exists():
        print(f"错误: 未找到 {graph_html}，请先在项目根目录执行 graphify update . 生成图谱")
        return 1

    # ---- 1. 汉化 graph.html ----
    html = graph_html.read_text(encoding="utf-8")
    already = "搜索节点" in html

    replacements = {
        '<html lang="en">': '<html lang="zh-CN">',
        "<title>graphify - graphify-out/graph.html</title>": "<title>知识图谱 - BMS</title>",
        'placeholder="Search nodes..."': 'placeholder="搜索节点..."',
        "<h3>Node Info</h3>": "<h3>节点信息</h3>",
        "Click a node to inspect it": "点击节点查看详情",
        "<h3>Communities</h3>": "<h3>社区</h3>",
        ">Select All<": ">全选<",
    }
    for key, value in replacements.items():
        if key in html:
            html = html.replace(key, value)

    html = re.sub(r"(\d+) nodes &middot; (\d+) edges &middot; (\d+) communities",
                  r"\1 节点 · \2 关系 · \3 社区", html)

    if not already:
        graph_html.write_text(html, encoding="utf-8")
        print(f"已汉化: {graph_html}")
    else:
        print(f"已汉化过（幂等跳过）: {graph_html}")

    # ---- 2. 生成中文 callflow 架构图 ----
    if not args.skip_callflow:
        result = subprocess.run(
            ["graphify", "export", "callflow-html", "--lang", "zh-CN", "--output", args.callflow_output],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        for line in (result.stdout or "").splitlines()[-3:]:
            print(line)
        callflow = Path(args.callflow_output)
        if callflow.exists():
            print(f"已生成中文架构图: {callflow}")
        else:
            print(f"警告: callflow-html 生成失败，请检查 graphify export callflow-html --help")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())