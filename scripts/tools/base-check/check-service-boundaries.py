#!/usr/bin/env python3
"""服务边界机器护栏（bms 权威源侧，CI base-integrity 与本地运行）。

工作区形态（`backend/libs/<共享库>` + `backend/services/<服务>`）下校验四项
（《后端开发规范》§3.1「依赖方向」、§3.2「模块边界与数据所有权」；《微服务演进规划》S1）：

1. **共享库不得依赖服务**：`libs/*` 包不得 import 任一 `services/*` 包；
2. **服务不得互相依赖**：任一服务包不得 import 另一服务包；
3. **分层依赖单向**：共享库 `core → {api, services}`、`repositories → services` 禁止；
   服务内 `api → services → repositories → models/schemas` 单向，`models/schemas` 不得反向；
4. **跨包不得引用私有实现**：跨包 import 目标模块含下划线前缀（模块内部实现）即失败。

用法::

    python3 scripts/tools/base-check/check-service-boundaries.py [bms 仓库根]
    python3 scripts/tools/base-check/check-service-boundaries.py --self-test
"""

import ast
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ".").resolve()

# 分层反向依赖黑名单：源子包 → 禁止依赖的目标子包
_SHARED_LAYER_RULES: dict[str, frozenset[str]] = {
    "core": frozenset({"api", "services"}),
    "repositories": frozenset({"services"}),
}
_SERVICE_LAYER_RULES: dict[str, frozenset[str]] = {
    "services": frozenset({"api"}),
    "repositories": frozenset({"api", "services"}),
    "models": frozenset({"api", "services", "repositories"}),
    "schemas": frozenset({"api", "services", "repositories"}),
}

problems: list[str] = []


def _discover_packages() -> dict[str, tuple[Path, bool]]:
    """发现工作区包：`{包名: (源码目录, 是否共享库)}`。

    Returns:
        dict[str, tuple[Path, bool]]: 包名 → （包根，是否共享库）。
    """
    packages: dict[str, tuple[Path, bool]] = {}
    for kind, shared in (("libs", True), ("services", False)):
        base = ROOT / "backend" / kind
        if not base.is_dir():
            continue
        for project in sorted(base.iterdir()):
            src = project / "src"
            if not src.is_dir():
                continue
            for pkg in sorted(src.iterdir()):
                if pkg.is_dir() and (pkg / "__init__.py").is_file():
                    packages[pkg.name] = (pkg, shared)
    return packages


def _iter_imports(path: Path) -> list[tuple[int, str]]:
    """解析文件并产出受管包导入（任意工作区包名开头）。

    Args:
        path: Python 源文件路径。

    Returns:
        list[tuple[int, str]]: 行号与导入模块名。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else []
        else:
            continue
        found.extend((node.lineno, module) for module in modules)
    return found


def _subpackage(package: str, root: Path, path: Path) -> str:
    """取源文件子包名（包根下文件返回包名）。

    Args:
        package: 包名。
        root: 包根目录。
        path: 源文件路径。

    Returns:
        str: 子包名。
    """
    rel = path.relative_to(root).as_posix()
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else package


def check() -> int:
    """执行四项护栏检查。

    Returns:
        int: 违规项数。
    """
    packages = _discover_packages()
    names = set(packages)
    for package, (root, shared) in packages.items():
        layer_rules = _SHARED_LAYER_RULES if shared else _SERVICE_LAYER_RULES
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            source = _subpackage(package, root, path)
            for lineno, module in _iter_imports(path):
                top = module.split(".")[0]
                if top not in names:
                    continue
                detail = f"{rel}:{lineno} import {module}"
                target_shared = packages[top][1]
                if shared and not target_shared:
                    problems.append(f"[共享库依赖服务] {detail}")
                if not shared and top != package and not target_shared:
                    problems.append(f"[服务互相依赖] {detail}")
                parts = module.split(".")
                target = parts[1] if len(parts) > 1 else top
                if top == package and target in layer_rules.get(source, frozenset()):
                    problems.append(f"[分层反向依赖] {detail}")
                if top != package and any(part.startswith("_") for part in parts[1:]):
                    problems.append(f"[跨包私有引用] {detail}")
    return len(problems)


def _self_test() -> int:
    """护栏拦截自检：在临时仓库构造违规样例，断言脚本报错。"""
    import subprocess
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        core = tmp_path / "backend/libs/bms_core/src/bms_core"
        svc = tmp_path / "backend/services/platform/src/bms_platform"
        (core / "core").mkdir(parents=True)
        (core / "__init__.py").write_text("", encoding="utf-8")
        (core / "core/__init__.py").write_text("", encoding="utf-8")
        (svc / "api").mkdir(parents=True)
        (svc / "__init__.py").write_text("", encoding="utf-8")
        (svc / "api/__init__.py").write_text("", encoding="utf-8")

        def run(expect_fail: bool, label: str) -> None:
            nonlocal ok
            result = subprocess.run([sys.executable, os.path.abspath(__file__), str(tmp_path)], capture_output=True, text=True)
            failed = result.returncode != 0
            passed = failed == expect_fail
            ok = ok and passed
            print(f"  [self-test] {label}：{'通过' if passed else '不通过'}（期望{'拦截' if expect_fail else '放行'}）")

        (svc / "api/router.py").write_text("import bms_core\n", encoding="utf-8")
        run(False, "服务依赖共享库放行")

        (core / "core/probe.py").write_text("import bms_platform\n", encoding="utf-8")
        run(True, "共享库依赖服务拦截")

        (core / "core/probe.py").write_text("import bms_core\n", encoding="utf-8")
        (svc / "api/router.py").write_text("from bms_core.repositories import base_repository\n", encoding="utf-8")
        run(False, "合规导入放行")
    return 0 if ok else 1


def main() -> int:
    """入口：执行护栏或自检。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    if "--self-test" in sys.argv:
        return _self_test()
    count = check()
    if count:
        print(f"\n[check-service-boundaries] 不通过：{count} 项")
        for problem in problems:
            print("  " + problem)
        return 1
    print("[check-service-boundaries] 通过：共享库 / 服务边界与分层依赖单向。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
