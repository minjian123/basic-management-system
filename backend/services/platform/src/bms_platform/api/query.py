"""通用查询参数解析（平台服务内共用）。

- 只放**与业务无关**的形态解析，不承载筛选语义；
- 非法输入一律 `ParamError`（10001），不静默忽略；
- 集合声明使用插入序并发集合类（与基座口径一致）。
"""

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError

__all__ = ["MAX_ID_FILTER", "parse_id_list"]

MAX_ID_FILTER = 200
"""单次按主键批量过滤的上限（防超长 `IN (...)`；与列表页页长上限同量级）。"""


def parse_id_list(raw: str | None, *, field: str = "ids") -> ConcurrentStableList[int]:
    """解析逗号分隔的主键清单。

    Args:
        raw: 原始查询参数（如 `ids=1,2,3`；None / 空串 / 仅逗号视为未指定）。
        field: 参数名（错误文案用）。

    Returns:
        ConcurrentStableList[int]: 主键清单（去空白、保序、去重）。

    Raises:
        ParamError: 含非整数 / 非正数项，或超过 :data:`MAX_ID_FILTER`（10001）。
    """
    ids: ConcurrentStableList[int] = ConcurrentStableList()
    for part in (raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        if not text.isdigit() or int(text) <= 0:
            raise ParamError(f"{field} 需为正整数：{text}")
        value = int(text)
        if value not in ids:
            ids.add(value)
    if len(ids) > MAX_ID_FILTER:
        raise ParamError(f"{field} 单次最多 {MAX_ID_FILTER} 项")
    return ids
