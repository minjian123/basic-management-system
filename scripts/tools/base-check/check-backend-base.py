#!/usr/bin/env python3
"""后端基座合规对账（bms 权威源侧，CI 与本地运行）。

校验三项（《后端审计规范》B1 / B5 / B6 / B9 的机器化）：

1. **继承链对账**：《后端基类清单》§10「继承链与代码位置」的 `A → B → …` 链条
   ↔ 代码 `backend/app/**` 的 `class A(B)` 相邻关系；
2. **错误码段位**：`app/core/error_codes.py` 的平台码为 5 位且万位落在平台段（1~9）、
   无产品段（10xxxx 起）混入；
3. **迁移链完整**：`backend/alembic/versions/*.py` 的 `revision` / `down_revision`
   构成单链（唯一 head、无断链）。

用法::

    python3 scripts/tools/base-check/check-backend-base.py [bms 仓库根]
"""

import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
MANIFEST = os.path.join(ROOT, "bms文档/后端基类清单.md")
APP_DIR = os.path.join(ROOT, "backend/app")
ERROR_CODES = os.path.join(ROOT, "backend/app/core/error_codes.py")
VERSIONS_DIR = os.path.join(ROOT, "backend/alembic/versions")

problems: list[str] = []
checked_chains = 0

PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
CLASS_RE = re.compile(r"^class\s+(\w+)(?:\[[^\]]*\])?\s*\(([^)]*)\)", re.M)


def parse_chains(raw_line: str) -> list[tuple[str, ...]]:
    """解析清单链条目：支持 `` `A` / `B` → `C` / `D` `` 组配对与 `+` 多父类说明。

    - 去括号注释与反引号；按 `→` 切段、按 `/` 切组；
    - 组内非法标识符（中文占位 / `Sorted*` 等）过滤后：各组等长（或长度为 1 的广播）→
      逐项配对成链；否则跳过。
    """
    line = PAREN_RE.sub("", raw_line).replace("`", "")
    if "→" not in line:
        return []
    # 链间分隔（顿号 / 全角逗号 / 分号）：逐条独立解析（避免跨链错配）
    if any(sep in line for sep in ("、", "，", "；")):
        chains: list[tuple[str, ...]] = []
        for part in re.split(r"[、，；]", line):
            chains.extend(parse_chains(part))
        return chains
    segments = [seg for seg in line.split("→")]
    groups: list[list[str]] = []
    for seg in segments:
        # 段内可能混中文说明（如「链路 `NullX`」）：先删 `Xxx*` 占位，再提取标识符；
        # 仅保留含小写字母者（类名惯例 PascalCase），滤掉中文描述中的全大写缩写（LLM / SSO）
        cleaned = re.sub(r"[A-Za-z_][A-Za-z0-9_]*\*", "", seg)
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cleaned)
        groups.append([word for word in words if re.search(r"[a-z]", word)])
    groups = [group for group in groups if group]
    if not groups:
        return []
    length = max(len(group) for group in groups)
    if not all(len(group) in (1, length) for group in groups):
        return []
    return [
        tuple(group[0] if len(group) == 1 else group[index] for group in groups)
        for index in range(length)
    ]


def index_classes() -> dict[str, list[list[str]]]:
    """类名 → 父类名列表（重复定义保留全部）。"""
    index: dict[str, list[list[str]]] = {}
    for dp, _, files in os.walk(APP_DIR):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dp, name)
            text = open(path, encoding="utf-8", errors="ignore").read()
            for cls, bases in CLASS_RE.findall(text):
                parents = [
                    re.sub(r"\[.*\]", "", b.strip().split(".")[-1]) for b in bases.split(",") if b.strip()
                ]
                index.setdefault(cls, []).append(parents)
    return index


def check_inheritance(index: dict[str, list[list[str]]]) -> int:
    global checked_chains
    text = open(MANIFEST, encoding="utf-8").read()
    section = text[text.index("## 10. 继承链与代码位置") : text.index("## 11.")]
    for raw_line in section.splitlines():
        for chain in parse_chains(raw_line):
            for parent, child in zip(chain, chain[1:]):
                checked_chains += 1
                definitions = index.get(parent)
                if not definitions:
                    problems.append(f"[继承链] 清单登记 `{parent}` 起始链，但代码未找到该类（链：{' → '.join(chain)}）")
                    continue
                if not any(child in parents for parents in definitions):
                    found = " | ".join(",".join(p) or "object" for p in definitions)
                    problems.append(
                        f"[继承链] `{parent}` 应为 `{child}` 子类，实际父类：{found}（链：{' → '.join(chain)}）"
                    )
    return checked_chains


def check_manifest_coverage(index: dict[str, list[list[str]]]) -> int:
    """双向对账（B5 补充）：直接继承 `BaseObject` 的基座类必须出现在《后端基类清单》文本中。"""
    manifest_text = open(MANIFEST, encoding="utf-8").read()
    classes = [
        name
        for name, definitions in index.items()
        if not name.startswith("_") and any("BaseObject" in parents for parents in definitions)
    ]
    for name in sorted(classes):
        if not re.search(rf"\b{name}\b", manifest_text):
            problems.append(f"[清单对账] 直接继承 BaseObject 的 `{name}` 未在《后端基类清单》登记")
    return len(classes)


def check_error_segments() -> int:
    text = open(ERROR_CODES, encoding="utf-8").read()
    body = text[text.index("class ErrorCode") :]
    count = 0
    for name, raw in re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)\s*=\s*(\d+)", body, re.M):
        value = int(raw)
        count += 1
        if not (10000 <= value <= 99999):
            problems.append(f"[错误码] {name} = {value} 不是 5 位平台码（产品段 10xxxx 起不得混入）")
            continue
        if str(value)[0] not in "123456789":
            problems.append(f"[错误码] {name} = {value} 万位段超出平台段（1~9）")
    return count


def check_alembic_chain() -> int:
    if not os.path.isdir(VERSIONS_DIR):
        problems.append("[迁移链] 未找到 backend/alembic/versions/")
        return 0
    revisions: dict[str, str | None] = {}
    for name in os.listdir(VERSIONS_DIR):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(VERSIONS_DIR, name), encoding="utf-8", errors="ignore").read()
        rev = re.search(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)", text, re.M)
        down = re.search(r"^down_revision[^=]*=\s*(None|[\"']([^\"']+)[\"'])", text, re.M)
        if not rev:
            problems.append(f"[迁移链] {name} 缺少 revision 定义")
            continue
        parent = None if (not down or down.group(1) == "None") else down.group(2)
        revisions[rev.group(1)] = parent
    if not revisions:
        print("  （迁移版本目录为空——迁移随后续阶段建立，跳过链检查）")
        return 0
    heads = [r for r in revisions if r not in {p for p in revisions.values() if p}]
    if len(heads) != 1:
        problems.append(f"[迁移链] head 应为 1 个，实际 {len(heads)} 个：{', '.join(sorted(heads))}")
    for rev, parent in revisions.items():
        if parent and parent not in revisions:
            problems.append(f"[迁移链] {rev} 的 down_revision「{parent}」不存在（断链）")
    return len(revisions)


def self_test() -> int:
    """fixture 拦截自检（《后端审计规范》§8：护栏须可验证拦截）。

    在临时目录构造「清单 vs 代码」违规样例，断言脚本报错。
    """
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "bms文档"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "backend/app/core"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "backend/alembic/versions"), exist_ok=True)
        open(os.path.join(tmp, "bms文档/后端基类清单.md"), "w", encoding="utf-8").write(
            "# 清单\n\n## 10. 继承链与代码位置\n\n- `BadChild → BaseObject`。\n\n## 11. 扩展\n"
        )
        open(os.path.join(tmp, "backend/app/core/probe.py"), "w", encoding="utf-8").write(
            "class BaseObject:\n    pass\n\n\nclass BadChild(BaseObject):  # 多父类违规样例：清单要求直接 BaseObject 时会漏检——反向样例\n    pass\n\n\nclass Orphan:\n    pass\n"
        )
        open(os.path.join(tmp, "backend/app/core/error_codes.py"), "w", encoding="utf-8").write(
            'class ErrorCode:\n    OK = 10001\n'
        )

        def run_case(name: str, expect_fail: bool) -> None:
            nonlocal ok
            import subprocess

            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), tmp],
                capture_output=True,
                text=True,
            )
            failed = result.returncode != 0
            passed = failed == expect_fail
            ok = ok and passed
            print(f"  [self-test] {name}：{'通过' if passed else '不通过'}（期望{'拦截' if expect_fail else '放行'}，实际{'拦截' if failed else '放行'}）")

        # 1) 正向：清单链与代码一致 → 放行
        run_case("清单与代码一致", expect_fail=False)
        # 2) 反向：清单登记未存在的类 → 拦截（继承链缺类）
        open(os.path.join(tmp, "bms文档/后端基类清单.md"), "w", encoding="utf-8").write(
            "# 清单\n\n## 10. 继承链与代码位置\n\n- `GhostClass → BaseObject`。\n\n## 11. 扩展\n"
        )
        run_case("清单登记未存在的类", expect_fail=True)
        # 3) 错误码越段（100001 / 万位 0）→ 拦截
        open(os.path.join(tmp, "bms文档/后端基类清单.md"), "w", encoding="utf-8").write(
            "# 清单\n\n## 10. 继承链与代码位置\n\n## 11. 扩展\n"
        )
        open(os.path.join(tmp, "backend/app/core/error_codes.py"), "w", encoding="utf-8").write(
            'class ErrorCode:\n    OK = 10001\n    BAD = 100001\n'
        )
        run_case("错误码越段", expect_fail=True)
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    index = index_classes()
    chains = check_inheritance(index)
    covered = check_manifest_coverage(index)
    codes = check_error_segments()
    revs = check_alembic_chain()
    print(f"1. 继承链对账：检查 {chains} 条相邻关系（清单 §10 ↔ 代码）")
    print(f"2. 清单对账（补充）：直接继承 BaseObject 的 {covered} 个基座类均已登记")
    print(f"3. 错误码段位：检查 {codes} 个平台码")
    print(f"4. 迁移链：检查 {revs} 个 revision")
    if problems:
        print(f"\n[check-backend-base] 不通过：{len(problems)} 项")
        for problem in problems:
            print("  " + problem)
        return 1
    print("\n[check-backend-base] 通过：继承链 / 错误码段位 / 迁移链全部对齐。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
