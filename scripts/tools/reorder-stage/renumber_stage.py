"""开发阶段编号重排：17 阶段 -> 19 阶段。

插入两个新阶段：
    三 后端插件化（在 二 后端基座 之后）
    五 前端插件化（在 四 前端组件库 之后）

映射（旧 -> 新）：一/二 不变；三 -> 四；四 ~ 十七 -> +2。

用法：在 bms 仓库根运行
    python3 scripts/tools/reorder-stage/renumber_stage.py [--dry-run]

实现要点：
- 单趟正则替换，避免「阶段三 前端组件库」被「阶段」前缀与「阶段名」两条规则连续命中造成双重 +2。
- 范围写法（阶段九~十三）单独成支，后缀数字无「阶段」前缀也能正确映射。
- 十八 / 十九 为新值，映射为自身，防止被二次识别。
"""

from __future__ import annotations

import pathlib
import re
import sys

DRY = "--dry-run" in sys.argv

ROOT = pathlib.Path("bms文档")

CN_MAP = {
    "一": "一",
    "二": "二",
    "三": "四",
    "四": "六",
    "五": "七",
    "六": "八",
    "七": "九",
    "八": "十",
    "九": "十一",
    "十": "十二",
    "十一": "十三",
    "十二": "十四",
    "十三": "十五",
    "十四": "十六",
    "十五": "十七",
    "十六": "十八",
    "十七": "十九",
    # 新值：映射为自身，防止二次命中
    "十八": "十八",
    "十九": "十九",
}

_ORDER = "一二三四五六七八九十"
CN_ALT = "|".join(sorted(CN_MAP, key=lambda k: (-len(k), _ORDER.index(k[0]))))

STAGE_NAMES = (
    "项目骨架|后端基座|前端组件库|认证与安全|RBAC基础模块|RBAC|通用能力|"
    "工作流引擎|系统集成与消息|业务外置注记|业务外置|分布式与监控|"
    "性能加固与压测|性能加固|前端全页面|报表BI|报表|移动端H5|移动端|"
    "全文检索|AI能力|AI"
)

RE_COUNT = re.compile(r"17\s*个开发阶段")

# 单趟替换：范围 > 阶段+名 > 阶段前缀 > 裸数字+阶段名
RE_ALL = re.compile(
    rf"阶段({CN_ALT})\s*[~～-]\s*({CN_ALT})"          # 1,2 范围
    rf"|阶段({CN_ALT})(\s+)({STAGE_NAMES})"           # 3,4,5 阶段+名
    rf"|阶段({CN_ALT})"                               # 6 阶段前缀
    rf"|({CN_ALT})(\s+)({STAGE_NAMES})"               # 7,8,9 裸数字+名
)


def _sub(m: re.Match) -> str:
    if m.group(1):  # 范围
        return f"阶段{CN_MAP[m.group(1)]}~{CN_MAP[m.group(2)]}"
    if m.group(3):  # 阶段 + 名
        return f"阶段{CN_MAP[m.group(3)]}{m.group(4)}{m.group(5)}"
    if m.group(6):  # 阶段前缀
        return f"阶段{CN_MAP[m.group(6)]}"
    return f"{CN_MAP[m.group(7)]}{m.group(8)}{m.group(9)}"  # 裸数字 + 名


EXCLUDE_PARTS = {
    "资料/知识档案/插件化架构",  # 插件化自身三阶段，非开发阶段
    "资源/vendor",
    "设计/原型设计/资源",
}
EXCLUDE_SUFFIX = (".min.js", ".min.css")

RESTORE = {
    "@@PLUG_BE@@": "三 后端插件化",
    "@@PLUG_FE@@": "五 前端插件化",
}

RE_ACCEPT_BE = re.compile(r"(\| 后端插件化 \|[^|]*\|)\s*二\s*\|")
RE_ACCEPT_FE = re.compile(r"(\| 前端插件化 \|[^|]*\|)\s*三\s*\|")


def iter_files():
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in {".md", ".html"}:
            continue
        if p.name.endswith(EXCLUDE_SUFFIX):
            continue
        rel = p.as_posix()
        if any(x in rel for x in EXCLUDE_PARTS):
            continue
        yield p


def convert(text: str) -> str:
    # 1) 保护新增阶段行（它们的编号是新值，不参与旧->新映射）
    text = text.replace("二 后端插件化", "@@PLUG_BE@@")
    text = text.replace("三 前端插件化", "@@PLUG_FE@@")
    # 2) 验收表「关联阶段」列
    text = RE_ACCEPT_BE.sub(r"\1 三 |", text)
    text = RE_ACCEPT_FE.sub(r"\1 五 |", text)
    # 3) 通用重排（单趟）
    text = RE_ALL.sub(_sub, text)
    text = RE_COUNT.sub("19 个开发阶段", text)
    # 4) 还原
    for token, final in RESTORE.items():
        text = text.replace(token, final)
    return text


def main() -> None:
    changed = 0
    total = 0
    for p in iter_files():
        src = p.read_text(encoding="utf-8")
        dst = convert(src)
        if src == dst:
            continue
        n = sum(1 for a, b in zip(src.splitlines(), dst.splitlines()) if a != b)
        total += n
        changed += 1
        print(f"{n:>4} 行  {p.as_posix()}")
        if not DRY:
            p.write_text(dst, encoding="utf-8")
    print(
        f"\n合计：{changed} 个文件，{total} 行改动"
        + ("（dry-run，未写入）" if DRY else "")
    )


if __name__ == "__main__":
    main()
