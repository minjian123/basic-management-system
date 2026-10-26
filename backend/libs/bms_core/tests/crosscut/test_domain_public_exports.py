"""服务业务域公共出口契约（Kiwi 2359）：每域一个出口、可导入且出口稳定。

口径（D2）：跨域引用只经 `domains/<域>/public.py`；无跨域使用方的域也须保证模块可导入、
`__all__` 为空 `list`（形态一致，便于后续按需显式增补）。
"""

import importlib
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList

_PUBLIC_MODULES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "bms_ai.domains.ai.public",
        "bms_file.domains.file.public",
        "bms_identity.domains.identity_federation.public",
        "bms_notification.domains.notification.public",
        "bms_report.domains.report.public",
        "bms_search.domains.search.public",
        "bms_tenant.domains.tenant.public",
        "bms_txn.domains.txn.public",
    )
)
"""8 个服务业务域的公共出口模块（无跨域使用方时为空占位）。"""


@pytest.mark.kiwi_id(2359)
@pytest.mark.parametrize("module_name", list(_PUBLIC_MODULES))
def test_domain_public_module_importable(module_name: str) -> None:
    """公共出口模块可导入；`__all__` 为空 `list` 且不导出任何名字（空占位形态一致）。"""
    module: Any = importlib.import_module(module_name)
    exports = cast("list[str]", module.__all__)
    names = cast("dict[str, Any]", vars(module))

    assert isinstance(exports, list)
    assert exports == []
    assert [name for name in names if not name.startswith("_")] == []
