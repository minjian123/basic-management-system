"""测试产物落点基址（会话起始钉定工程根）。

**为什么单独成模块**：`fixtures` 与 `namespace` 都要用基址，而 `fixtures` 依赖 `namespace`
（命名空间助手）——基址若写在 `fixtures` 里会形成循环导入。基址是纯粹的「进程级路径状态」，
单独放置后两处同源。

**为什么要钉定**：`Path.cwd()` 是进程级可变状态，而共享测试库（`platform` / `tenant`）是**会话级**
单例。若某条用例中途 `chdir` 后第一次解析共享库夹具，库就会落到临时目录，后续用例连到另一个路径
（表现为随机的「no such table」）。会话起始把基址钉在工程根上，用例 `chdir` 就不再有影响。
"""

from pathlib import Path

_project_root: Path | None = None
"""已钉定的工程根（`None` 表示未钉定，按当前工作目录解析）。"""


def configure_project_root(value: str) -> None:
    """钉定基址，空串表示取消钉定（回落到当前工作目录）。

    Args:
        value: 工程根路径。
    """
    global _project_root
    _project_root = Path(value) if value else None


def project_root() -> Path:
    """测试产物基址（已钉定的工程根，否则当前工作目录）。

    Returns:
        Path: 基址目录。
    """
    return _project_root if _project_root is not None else Path.cwd()
