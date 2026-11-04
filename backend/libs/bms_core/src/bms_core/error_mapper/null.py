"""error_mapper 能力域缺省实现（Null Object）：原样返回、无副作用。"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import BizError
from bms_core.error_mapper.base import BaseErrorMapper

__all__ = [
    "NullErrorMapper",
]


class NullErrorMapper(BaseErrorMapper, BaseNullObject):
    """占位覆盖器：不改写（未配置产品码覆盖时使用，渲染结果与接入前一致）。"""

    def map(self, exc: BizError) -> BizError:
        """原样返回异常。

        Args:
            exc: 原始业务异常。

        Returns:
            BizError: 传入的异常本身。
        """
        return exc
