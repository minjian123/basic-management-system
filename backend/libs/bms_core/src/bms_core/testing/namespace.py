"""用例命名空间助手（04-6-1）：单库叠加语义的唯一写法。

为什么需要：测试库从“每用例一套干净库”改为“每逻辑数据源一套库 + 用例叠加”后，用例必须
自己划出**唯一命名空间**（编码 / 前缀 / 业务键），查询与断言一律限定在该命名空间内，否则会读到
前序用例的数据。本模块把“唯一编码 / 断言限定 / 查询过滤”三件事收成一处，避免各用例自创写法。

口径（《测试规范》「测试数据」节）：

- 前缀由 `nodeid` 稳定派生（同用例跨会话一致），并带 worker 位，保证并行进程互不相交；
- 断言只认本命名空间内的数据；无法按前缀过滤的全局统计改用 `assert_delta` 做相对增量；
- 禁止用固定编码 / 固定哨兵当业务键，禁止对全表做条数断言。
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.testing.paths import project_root

PREFIX_MAX_LEN = 16
"""前缀长度上限（避免撞上业务编码的长度校验）。"""

_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
"""业务后缀允许的字符集与长度。"""

_PREFIX_RE = re.compile(r"^w[0-9][0-9a-f]{8}$")
"""前缀形态：`w{worker}{nodeid 摘要 8 位}`。"""


class Namespace:
    """一条用例的命名空间（唯一前缀 + 生成 / 过滤 / 断言能力）。

    Attributes:
        prefix: 唯一前缀（`w{worker}{digest8}`），同时作为业务编码前缀与 LIKE 模式基。
    """

    def __init__(self, prefix: str) -> None:
        """初始化。

        Args:
            prefix: 唯一前缀；不合规直接抛错（不静默截断，避免撞键）。

        Raises:
            ValueError: 前缀形态非法或超长。
        """
        if len(prefix) > PREFIX_MAX_LEN or not _PREFIX_RE.match(prefix):
            raise ValueError(
                f"命名空间前缀非法：{prefix!r}（应为 w{{worker}}{{8 位十六进制}}，长度 ≤ {PREFIX_MAX_LEN}）"
            )
        self.prefix = prefix

    def __repr__(self) -> str:
        """调试表示。

        Returns:
            str: 形如 `Namespace('w0a1b2c3d4')`。
        """
        return f"Namespace({self.prefix!r})"

    def code(self, suffix: str) -> str:
        """生成带前缀的业务编码 / 名称。

        Args:
            suffix: 业务后缀（小写字母 / 数字 / `_` / `-`，≤32 位）。

        Returns:
            str: `{prefix}-{suffix}`。

        Raises:
            ValueError: 后缀为空或含非法字符。
        """
        if not _SUFFIX_RE.match(suffix):
            raise ValueError(f"命名空间后缀非法：{suffix!r}（应匹配 {_SUFFIX_RE.pattern}）")
        return f"{self.prefix}-{suffix}"

    def like(self) -> str:
        """SQL `LIKE` 用的模式串。

        Returns:
            str: `{prefix}%`。
        """
        return f"{self.prefix}%"

    def owns(self, value: object) -> bool:
        """判断取值是否属于本命名空间。

        Args:
            value: 待判断的编码 / 名称（非字符串视为不属于）。

        Returns:
            bool: 以本前缀开头为 True。
        """
        return isinstance(value, str) and value.startswith(f"{self.prefix}-")


def worker_tag() -> str:
    """当前执行 worker 的前缀位。

    Returns:
        str: 串行 `0`，xdist `gwN` 取 `N`（超过 9 时取末位，保证单字符位宽）。
    """
    name = os.environ.get("PYTEST_XDIST_WORKER", "")
    if name.startswith("gw") and name[2:].isdigit():
        return str(int(name[2:]) % 10)
    return "0"


def prefix_for(nodeid: str) -> str:
    """按用例 nodeid 派生稳定前缀。

    Args:
        nodeid: pytest 用例标识（`路径::类::函数`）。

    Returns:
        str: `w{worker}{nodeid 摘要 8 位}`。
    """
    digest = hashlib.sha1(nodeid.encode("utf-8")).hexdigest()[:8]
    return f"w{worker_tag()}{digest}"


def for_test(request: pytest.FixtureRequest) -> Namespace:
    """取当前用例的命名空间，并登记「前缀 → nodeid」映射。

    Args:
        request: pytest 夹具请求。

    Returns:
        Namespace: 当前用例命名空间。
    """
    nodeid = str(getattr(cast("Any", request).node, "nodeid", ""))
    namespace = Namespace(prefix_for(nodeid))
    _record(namespace.prefix, nodeid)
    return namespace


def scoped(statement: Any, column: Any, namespace: Namespace) -> Any:
    """给查询追加命名空间前缀过滤。

    Args:
        statement: SQLAlchemy `Select`（或其他支持 `.where()` 的语句对象）。
        column: 参与过滤的列（通常是业务编码列）。
        namespace: 命名空间。

    Returns:
        Any: 追加过滤后的语句。
    """
    return statement.where(column.like(namespace.like()))


def _field_value(row: Any, field: str) -> object:
    """取行内字段值（兼容 ORM 对象与字典）。

    Args:
        row: 行对象。
        field: 字段名。

    Returns:
        object: 字段值；缺失返回 `None`。
    """
    if isinstance(row, dict):
        return cast("dict[str, object]", row).get(field)
    return getattr(row, field, None)


def assert_scoped(rows: Iterable[Any], namespace: Namespace, *, field: str = "code") -> None:
    """断言集合内的数据全部属于本命名空间。

    Args:
        rows: 待断言的集合（ORM 对象或字典）。
        namespace: 命名空间。
        field: 业务编码字段名。

    Raises:
        AssertionError: 出现非本命名空间的数据（通常是固定编码 / 未加前缀过滤）。
    """
    strangers = [value for value in (_field_value(row, field) for row in rows) if not namespace.owns(value)]
    if strangers:
        raise AssertionError(
            f"集合含非本命名空间的数据（字段 {field}）：{strangers[:5]}；"
            "请改用 ns.code() 生成业务编码，并对查询加 scoped() 过滤"
        )


def assert_delta(before: int, after: int, *, expected: int = 1) -> None:
    """断言全局统计的相对增量。

    Args:
        before: 执行前计数。
        after: 执行后计数。
        expected: 期望增量（缺省 +1）。

    Raises:
        AssertionError: 增量不等于期望值。
    """
    if after - before != expected:
        raise AssertionError(f"计数增量不符：期望 {expected}，实得 {after - before}（before={before}, after={after}）")


def map_path(root: Path | None = None) -> Path:
    """命名空间映射文件路径（`.cache/test/namespace-map.jsonl`）。

    Args:
        root: 仓内基址（缺省取已钉定的工程根，未钉定时为当前工作目录）。

    Returns:
        Path: 映射文件路径（父目录自动创建）。
    """
    directory = (root or project_root()) / ".cache" / "test"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "namespace-map.jsonl"


def _record(prefix: str, nodeid: str) -> None:
    """追加一条「前缀 → nodeid」映射（供排查脏数据归属）。

    Args:
        prefix: 命名空间前缀。
        nodeid: 用例标识。
    """
    try:
        with map_path().open("a", encoding="utf-8") as handle:
            handle.write(f'{{"prefix": "{prefix}", "nodeid": "{nodeid}"}}\n')
    except OSError:
        # 映射只服务排查，写失败不影响用例结论
        return
