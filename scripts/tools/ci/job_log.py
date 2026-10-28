#!/usr/bin/env python3
"""打印指定 job 的日志（清洗后）。

`watch_pipeline.py` 只在终态失败时附日志尾部；排查时经常要看**任意** job 的日志，本脚本补这一块：
默认打印尾部，可只保留命中关键词的行，也可打全量。

用法::

    # 尾部 80 行
    python3 scripts/tools/ci/job_log.py bms:10041

    # 只看含 error / failed 的行（不区分大小写）
    python3 scripts/tools/ci/job_log.py bms:10041 --grep error

    # 全量
    python3 scripts/tools/ci/job_log.py bms:10041 --full

凭据与地址：与 `trigger.py` 同源（`deploy/.env` 或同名环境变量）。
退出码：0 成功；1 请求失败（job 不存在 / 日志已过期）；2 用法或凭据缺失。
"""

from __future__ import annotations

import argparse
import sys
import urllib.error

from ci_common import (
    REPO_NAMES,
    ConcurrentStableList,
    clean_trace_lines,
    get_text,
    load_api,
    missing_credentials_hint,
    quoted,
    tail,
)

DEFAULT_TAIL_LINES = 80
"""缺省打印的日志尾部行数。"""


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 成功 / 1 请求失败 / 2 用法或凭据缺失）。
    """
    parser = argparse.ArgumentParser(description="打印指定 job 的日志（清洗后）")
    parser.add_argument("target", help="目标，格式 <仓名>:<jobID>（job id 见 pipeline_jobs.py）")
    parser.add_argument("--tail", type=int, default=DEFAULT_TAIL_LINES, help=f"尾部行数（缺省 {DEFAULT_TAIL_LINES}）")
    parser.add_argument("--grep", default="", help="只保留含该关键词的行（不区分大小写）")
    parser.add_argument("--full", action="store_true", help="打印全量日志（忽略 --tail）")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    name, sep, raw_id = str(args.target).partition(":")
    if not sep or not name or not raw_id.isdigit():
        print("[log] 目标格式应为 <仓名>:<jobID>", file=sys.stderr)
        return 2
    api = load_api()
    if api is None:
        print(f"[log] {missing_credentials_hint()}", file=sys.stderr)
        return 2

    project = REPO_NAMES.get(name, name)
    try:
        text = get_text(api, f"projects/{quoted(project)}/jobs/{int(raw_id)}/trace")
    except urllib.error.HTTPError as exc:
        print(f"[log] {name}#{raw_id} 日志不可取：HTTP {exc.code}（job 不存在或日志已过期）", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"[log] {name}#{raw_id} 请求失败：{exc.reason}", file=sys.stderr)
        return 1

    lines = clean_trace_lines(text)
    keyword = str(args.grep).strip().lower()
    if keyword:
        lines = ConcurrentStableList(line for line in lines if keyword in line.lower())
    if not args.full:
        lines = tail(lines, int(args.tail))
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
