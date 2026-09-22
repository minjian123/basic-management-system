"""db 层读写绑定与请求方法判定。

- `WRITE_BINDING` / `READ_BINDING`：仓储 `_resolve_binding` 的绑定键（语义分离；
  本阶段主 / 副本由引擎与会话层按只读标记选引擎，绑定键供契约与断言使用）。
- `SAFE_METHODS` / `is_read_method`：请求方法 → 只读标记判定（只读中间件取用）。
"""

WRITE_BINDING = "default"
READ_BINDING = "replica"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_read_method(method: str | None) -> bool:
    """是否为只读安全方法（GET / HEAD / OPTIONS）。

    Args:
        method: HTTP 方法（大小写不敏感）。

    Returns:
        bool: 只读安全方法 True。
    """
    return (method or "").upper() in SAFE_METHODS
