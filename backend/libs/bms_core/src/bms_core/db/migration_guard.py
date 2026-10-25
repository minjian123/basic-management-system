"""迁移执行期校验与库级互斥（07C `03_02` §3.8）：护栏防「写错」，执行器防「撞上」。

**为什么不能只靠静态护栏**：冲突取决于**执行当时的库现状与清单全集**——两条域清单各自看都没问题，
合到同一库才撞表；版本记录表里出现别的库带来的版本号，也只有执行时才知道。故平台作为执行方自带校验：

| # | 校验 | 判定 | 失败处置 |
| --- | --- | --- | --- |
| 1 | 脚本目标表归属 | 清单内脚本操作的每张表必须**归属本清单的业务域** | 拒绝执行，指出域与表 |
| 2 | 清单表集不相交 | 同一库内各清单目标表集不得有交集 | 拒绝执行，指出相撞两域与表 |
| 3 | 版本记录表与清单一致 | 记录表 revision 必须存在于本清单（未知即拒） | 拒绝执行，输出未知 revision |
| 5 | 版本单调 | 待执行 revision 必须大于当前值，不允许回退 / 分叉（多 head 即拒） | 拒绝执行 |
| 6 | 破坏性操作 | `drop_table` / `drop_column` 须显式放行（`allow_destructive`） | **默认拒绝** |
| 7 | 库级互斥 | 取库级锁（PostgreSQL / MySQL）；拿不到即拒，不排队等待 | 拒绝并提示并发 |

**结构对账（第 4 项）不在本模块**：模型 ↔ 库现状的比对复用既有入口 `ops/check_tables.py`
（口径：不新增第二套对账实现，见《数据库开发规范》「与数据库设计的关联与事实源」节）。

**输出与退出码**：`preflight()` 返回问题清单；调用方任一项不过即**不执行任何脚本**（先全量预检、再执行，
不留半改状态），非零退出。
"""

import contextlib
import re
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.migration import MigrationSeries, has_revisions, unit_series

_CREATE_TABLE_RE = re.compile(r"op\.create_table\(\s*[\"']([a-z0-9_]+)[\"']")
_BATCH_TABLE_RE = re.compile(r"op\.batch_alter_table\(\s*[\"']([a-z0-9_]+)[\"']")
_ALTER_TABLE_RE = re.compile(r"op\.add_column\(\s*[\"']([a-z0-9_]+)[\"']")
_DROP_TABLE_RE = re.compile(r"op\.drop_table\(\s*[\"']([a-z0-9_]+)[\"']")
_DROP_COLUMN_RE = re.compile(r"op\.drop_column\(\s*[\"']([a-z0-9_]+)[\"']")
_REVISION_RE = re.compile(r"^(?:revision|down_revision)\s*[:=]")
_LOCK_KEYS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "postgresql": "bms:migration",
        "mysql": "bms_migration",
    }
)
"""库级锁键（PostgreSQL 咨询锁 / MySQL 命名锁；其余方言不提供库级锁，按部署串行）。"""


def script_tables(series: MigrationSeries) -> ConcurrentStableSet[str]:
    """清单内脚本操作的**目标表名**集合（建表 / 批量改表 / 加列）。

    Args:
        series: 清单定义。

    Returns:
        ConcurrentStableSet[str]: 表名集合（空清单为空集）。
    """
    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    location = series.version_location
    if not location.is_dir():
        return tables
    for script in sorted(location.glob("*.py")):
        content = script.read_text(encoding="utf-8", errors="ignore")
        for pattern in (_CREATE_TABLE_RE, _BATCH_TABLE_RE, _ALTER_TABLE_RE):
            tables.update(pattern.findall(content))
    return tables


def script_revisions(series: MigrationSeries) -> ConcurrentStableSet[str]:
    """清单内脚本声明的 revision 与 down_revision（未知版本号判定用）。

    Args:
        series: 清单定义。

    Returns:
        ConcurrentStableSet[str]: revision 字面集合。
    """
    revisions: ConcurrentStableSet[str] = ConcurrentStableSet()
    location = series.version_location
    if not location.is_dir():
        return revisions
    for script in sorted(location.glob("*.py")):
        for line in script.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not _REVISION_RE.match(line.strip()):
                continue
            _, _, raw = line.partition("=")
            for value in re.findall(r"[\"']([^\"']+)[\"']", raw):
                revisions.add(value)
    return revisions


def destructive_statements(series: MigrationSeries) -> ConcurrentStableList[str]:
    """清单内的破坏性操作明细（`drop_table` / `drop_column`）。

    Args:
        series: 清单定义。

    Returns:
        ConcurrentStableList[str]: 形如 `<脚本名>: drop table xxx` 的明细。
    """
    found: ConcurrentStableList[str] = ConcurrentStableList()
    location = series.version_location
    if not location.is_dir():
        return found
    for script in sorted(location.glob("*.py")):
        content = script.read_text(encoding="utf-8", errors="ignore")
        for table in _DROP_TABLE_RE.findall(content):
            found.add(f"{script.name}: drop table {table}")
        for table in _DROP_COLUMN_RE.findall(content):
            found.add(f"{script.name}: drop column @ {table}")
    return found


def check_script_ownership(series: MigrationSeries) -> ConcurrentStableList[str]:
    """校验 1：脚本目标表归属（全部须归本清单的业务域）。

    Args:
        series: 清单定义。

    Returns:
        ConcurrentStableList[str]: 越界明细（空表示通过）。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    for table in sorted(script_tables(series)):
        if table not in series.tables:
            problems.add(f"清单 {series.name} 的脚本操作了不属于该域的表：{table}")
    return problems


def check_series_disjoint(unit: str, datasource: str) -> ConcurrentStableList[str]:
    """校验 2：同一库内各清单目标表集不得相交（域间不得操作彼此的表）。

    Args:
        unit: 部署单元标识。
        datasource: 数据源段。

    Returns:
        ConcurrentStableList[str]: 相撞明细（空表示通过）。
    """
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    series_list = unit_series(unit, datasource)
    for index, left in enumerate(series_list):
        for right in series_list[index + 1 :]:
            shared = sorted(set(left.tables) & set(right.tables))
            if shared:
                problems.add(f"清单 {left.name} 与 {right.name} 目标表集相交：{', '.join(shared)}")
    return problems


def check_version_known(series: MigrationSeries, current: str | None) -> ConcurrentStableList[str]:
    """校验 3：版本记录表中的 revision 必须存在于本清单（未知即拒，防别的库 / 别的域带入）。

    Args:
        series: 清单定义。
        current: 版本记录表当前值（未迁移为 None）。

    Returns:
        ConcurrentStableList[str]: 未知 revision 明细（空表示通过）。
    """
    if not current:
        return ConcurrentStableList()
    if current in script_revisions(series):
        return ConcurrentStableList()
    return ConcurrentStableList([f"清单 {series.name} 的版本记录表出现未知 revision：{current}"])


def check_monotonic(series: MigrationSeries, current: str | None, head: str | None) -> ConcurrentStableList[str]:
    """校验 5：版本单调（不允许多 head / 分叉；当前值不在本清单即视为异常）。

    Args:
        series: 清单定义。
        current: 版本记录表当前值。
        head: 清单 head（无脚本为 None）。

    Returns:
        ConcurrentStableList[str]: 违规明细（空表示通过）。
    """
    if head is None:
        return ConcurrentStableList()
    if current and current not in script_revisions(series):
        return ConcurrentStableList([f"清单 {series.name} 的当前版本 {current} 不在本清单内（分叉或跨库污染）"])
    return ConcurrentStableList()


def check_destructive(series: MigrationSeries, *, allow_destructive: bool) -> ConcurrentStableList[str]:
    """校验 6：破坏性操作须显式放行（`drop table` / `drop column` 默认拒绝）。

    Args:
        series: 清单定义。
        allow_destructive: 调用方是否显式放行。

    Returns:
        ConcurrentStableList[str]: 未放行的破坏性操作明细。
    """
    if allow_destructive:
        return ConcurrentStableList()
    statements = destructive_statements(series)
    return ConcurrentStableList(f"清单 {series.name} 含破坏性操作（需显式放行）：{item}" for item in statements)


@contextlib.contextmanager
def library_lock(url: str) -> Generator[bool]:
    """校验 7：库级互斥（PostgreSQL 咨询锁 / MySQL 命名锁；其余方言不提供，按部署串行）。

    拿不到锁即返回 False（**不排队等待**，避免两实例同时改结构）。

    Args:
        url: 连接串。

    Yields:
        bool: 是否拿到锁（方言不支持时恒 True，由部署串行保证）。
    """
    backend = make_url(url).get_backend_name()
    key = _LOCK_KEYS.get(backend)
    if key is None:
        yield True
        return
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            if backend == "postgresql":
                statement = text("SELECT pg_try_advisory_lock(hashtext(:k))")
                acquired = bool(connection.execute(statement, {"k": key}).scalar())
            else:
                acquired = bool(connection.execute(text("SELECT GET_LOCK(:k, 0)"), {"k": key}).scalar())
            try:
                yield acquired
            finally:
                if acquired:
                    if backend == "postgresql":
                        connection.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": key})
                    else:
                        connection.execute(text("SELECT RELEASE_LOCK(:k)"), {"k": key})
    finally:
        engine.dispose()


class MigrationGuard(BaseFrameworkObject):
    """单库执行前的全量预检（列表 1/2/3/5/6 项；第 7 项由调用方经 `library_lock` 包住执行段）。"""

    def __init__(self, unit: str, datasource: str, *, allow_destructive: bool = False) -> None:
        """初始化。

        Args:
            unit: 部署单元标识。
            datasource: 数据源段。
            allow_destructive: 是否显式放行破坏性操作。
        """
        self.unit = unit
        self.datasource = datasource
        self.allow_destructive = allow_destructive

    def preflight(self) -> ConcurrentStableList[str]:
        """执行前全量预检（不连库的部分）。

        Returns:
            ConcurrentStableList[str]: 问题清单（空表示通过）。
        """
        problems: ConcurrentStableList[str] = ConcurrentStableList()
        problems.update(check_series_disjoint(self.unit, self.datasource))
        for series in unit_series(self.unit, self.datasource):
            if not has_revisions(series):
                continue
            problems.update(check_script_ownership(series))
            problems.update(check_destructive(series, allow_destructive=self.allow_destructive))
        return problems


def versions_dir(series: MigrationSeries) -> Path:
    """清单版本目录（执行期校验与脚本扫描共用）。

    Args:
        series: 清单定义。

    Returns:
        Path: 版本目录路径。
    """
    return series.version_location
