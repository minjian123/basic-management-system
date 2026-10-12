"""服务入口测试支撑：以非 `__main__` 名字执行 `<包>/__main__.py`。

服务入口模块的条件分支（`if __name__ == "__main__"`）两半都要覆盖：`runpy.run_module(..., run_name="__main__")`
覆盖「真」侧（启动经 `run_service`），本助手以**包内子模块名**执行同一文件覆盖「假」侧（常规导入不启动），
且**不往 `sys.modules` 写 `<包>.__main__`**（避免 `runpy` 的重复导入告警）。

探针名必须落在包命名空间内（`<包>._entrypoint_probe`）：覆盖率按 `source_pkgs`（`--cov=<包名>`）
以「模块名 → 包前缀」判定纳入，包外名（如 `<包>_entrypoint_probe`）会被判为不纳入并**缓存该否定决策**，
导致随后 `runpy` 的真侧执行同样不被记录。
"""

from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import cast

__all__ = ["load_entrypoint_source"]


def load_entrypoint_source(package_name: str) -> str:
    """以包内探针子模块名执行 `<package_name>/__main__.py`。

    Args:
        package_name: 服务包名（如 `bms_platform`）。

    Returns:
        str: 探针模块名（`<包>._entrypoint_probe`）。

    Raises:
        RuntimeError: 入口模块不可加载（缺 `__file__` / 无加载器）。
    """
    package = import_module(package_name)
    location = Path(cast("str", package.__file__)).parent / "__main__.py"
    probe_name = f"{package_name}._entrypoint_probe"
    spec = spec_from_file_location(probe_name, location)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"入口模块不可加载：{location}")
    spec.loader.exec_module(module_from_spec(spec))
    return probe_name
