"""产品错误码覆盖能力域：统一错误响应单点的「平台码 → 产品码」改写。

- 为什么需要：平台错误码在**中间件与全局异常处理器共用**的唯一渲染点 `build_error_response()` 出码；
  产品（如消息平台）自有错误码段，且要求「租户停用 / 不存在」对外给出产品码。基座在进入业务之前
  就返回平台码（`80002` / `80001`），产品侧原无改写点 → 由本能力域提供**唯一改写入口**。
- 取用：`build_error_response()` 先经 `apply_error_mapper(exc, provider)`；`provider` 取
  `[error_mapper].provider`，**空串 = 不覆盖**（原样返回、不解析插件，未配置产品的行为逐字节不变）。
- 实现：产品在 `configure_plugins()` 内登记（`plugin_key = "error_mapper"`），缺省 `NullErrorMapper`
  原样返回；映射结果须仍是 `BizError`，且产品负责保证目标码已登记（否则渲染走「未登记码」分支）。
- 降级：实现名解析失败（`PluginError`）时**原样返回原异常**——错误响应路径本身不可再抛错，
  否则 500 会掩盖原始业务错误；该分支同时记 `ERROR` 日志，暴露配置错配。
"""

from abc import ABC, abstractmethod
from typing import cast

from bms_core.core.exceptions import BizError, PluginError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "ERROR_MAPPER_KEY",
    "BaseErrorMapper",
    "apply_error_mapper",
]

ERROR_MAPPER_KEY = "error_mapper"
"""能力域键（`[error_mapper].provider` 的解析键）。"""

_LOGGER = get_logger("bms.error_mapper")


class BaseErrorMapper(BasePluggable, ABC):
    """错误码覆盖契约：把基座异常改写成产品异常（同一渲染单点生效）。"""

    key: str = "error_mapper"
    plugin_key: str = "error_mapper"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def map(self, exc: BizError) -> BizError:
        """改写异常（缺省实现原样返回；产品按自有码段映射）。

        Args:
            exc: 原始业务异常（中间件 / 端点上抛）。

        Returns:
            BizError: 改写后的异常（同一对象表示不改写）。
        """
        ...


def apply_error_mapper(exc: BizError, provider: str | None = None) -> BizError:
    """按配置的实现名改写异常（未配置实现名即原样返回）。

    Args:
        exc: 原始业务异常。
        provider: 配置的实现名（`[error_mapper].provider`；空串 / `None` 表示不覆盖）。

    Returns:
        BizError: 改写后的异常；未配置、解析失败或映射未命中时返回原异常。
    """
    if not provider:
        return exc
    try:
        mapper = cast(
            "BaseErrorMapper",
            resolve_plugin(ERROR_MAPPER_KEY, provider, expected_version=BaseErrorMapper.contract_version),
        )
    except PluginError:
        _LOGGER.error("error_mapper_unresolved", provider=provider, code=exc.code, error=repr(exc))
        return exc
    return mapper.map(exc)
