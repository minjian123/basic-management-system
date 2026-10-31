"""测试侧原生 SQL 的雪花 ID 参数助手（SQLite 补零口径）。

为什么需要：模型层 `SnowflakeId` 在 SQLite 落 38 位补零 `TEXT`，而原生 SQL 绕过类型层：

- 直接绑 int 会存成未补零文本，ORM 查询（补零）查不到；
- 超过 2^63 的 int 经 `sqlite3` 绑定会直接 `OverflowError`（即使列是 `TEXT`）。

测试里写原生 SQL 时，ID 参数一律经 `sqlite_id()` 转字符串；**生产代码禁止裸 SQL 操作 ID 列**。
"""

from bms_core.models.base import SQLITE_PADDED_WIDTH


def sqlite_id(value: int | str) -> str:
    """把雪花 ID 转为 SQLite 文本列的绑定值（38 位补零）。

    Args:
        value: 雪花 ID（int 或十进制字符串；已补零亦可）。

    Returns:
        str: 38 位补零字符串。
    """
    return str(int(value)).zfill(SQLITE_PADDED_WIDTH)


def sqlite_int(value: object) -> int:
    """把 SQLite 文本列读回的 ID 转回 int。

    Args:
        value: 数据库返回值（补零 / 未补零字符串，或 int）。

    Returns:
        int: 整数 ID。
    """
    return int(str(value))
