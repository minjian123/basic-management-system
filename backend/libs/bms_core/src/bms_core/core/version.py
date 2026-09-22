"""core 层版本基座：契约版本（`X.Y.Z`）解析与主版本兼容判定（插件 / 服务目录同源）。

- 契约版本为三段 semver 形态（`X.Y.Z`，段内按整数比较，允许前导零差异）；
  **主版本兼容 = 主版本号一致**（破坏性变更升主版本，见《架构设计 · 接口与集成》）。
- 插件机制（`core/plugin.py`）与服务目录契约登记（`services/module_registry.py`）
  共用本实现，避免版本解析口径分叉。
"""

import re

__all__ = ["CONTRACT_VERSION_RE", "contract_major"]

CONTRACT_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
"""契约版本格式（`X.Y.Z`；配合 `fullmatch` 使用）。"""


def contract_major(version: str) -> int | None:
    """取契约版本主版本号。

    Args:
        version: 契约版本字符串。

    Returns:
        int | None: 主版本号；非 `X.Y.Z` 返回 None。
    """
    if not CONTRACT_VERSION_RE.fullmatch(version):
        return None
    return int(version.split(".", 1)[0])
