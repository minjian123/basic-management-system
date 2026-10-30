"""发布清单运维入口（07C `04_01`）：参数解析、声明条目解析与跨库 revision 读取。

真库路径（`uv run python -m ops.release`）归部署窗口复验；本套用例只锁纯逻辑与读面选链。
"""

from dataclasses import dataclass

import pytest

import ops.release as release_ops
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList


@dataclass(frozen=True)
class _Series:
    """迁移清单替身（只含读面用到的两列）。"""

    datasource: str
    version_table: str


def test_parser_supports_six_commands() -> None:
    """子命令全集与公共参数：`--unit` 必填，`--declare` 可重复。"""
    parser = release_ops.build_parser()
    args = parser.parse_args(
        [
            "record",
            "--unit",
            "platform",
            "--declare",
            "role,0.1.0,0.1.0,0001",
            "--declare",
            "user,0.1.0,0.1.0,0001",
            "--note",
            "首次发布",
            "--allow-breaking",
        ]
    )
    assert args.command == "record"
    assert args.unit == "platform"
    assert args.tenant_scope == 0
    assert len(args.declare) == 2
    assert args.note == "首次发布"
    assert args.allow_breaking is True

    rollback = parser.parse_args(["rollback", "--unit", "platform", "--confirm", "--to-version", "2"])
    assert rollback.confirm is True
    assert rollback.to_version == 2


def test_declared_parsing() -> None:
    """声明条目：四段解析；段数不足或域为空即报错。"""
    entries = release_ops._declared(  # pyright: ignore[reportPrivateUsage]
        ConcurrentStableList(["role,0.1.0,0.1.0,0001", "user,0.2.0,0.2.0,"])
    )
    assert [(entry.domain_key, entry.service_version, entry.schema_revision) for entry in entries] == [
        ("role", "0.1.0", "0001"),
        ("user", "0.2.0", None),
    ]
    with pytest.raises(ValueError):
        release_ops._declared(ConcurrentStableList(["role,0.1.0"]))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError):
        release_ops._declared(ConcurrentStableList([",0.1.0,0.1.0,0001"]))  # pyright: ignore[reportPrivateUsage]


async def test_database_revisions_walks_series_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """读面按 `domain_series` 顺序取首个已初始化 revision；无连接串的链跳过。"""

    async def _fake_current(url: str, *, version_table: str, schema: str = "") -> str | None:
        """按库返回预设 revision（平台链已初始化、租户链未初始化）。

        Args:
            url: 连接串（本替身只看是否含 `tenant`）。
            version_table: 版本记录表名。
            schema: 模式名（忽略）。

        Returns:
            str | None: 预设 revision。
        """
        del schema
        if "tenant" in url:
            return None
        return "0001" if version_table.endswith("_alpha") else None

    monkeypatch.setattr(release_ops, "current_revision", _fake_current)

    def _series_of(domain: str) -> ConcurrentStableList[_Series]:
        """按域给出两条链的清单（平台链 + 租户链，记录表同名）。

        Args:
            domain: 业务域标识。

        Returns:
            ConcurrentStableList[_Series]: 清单替身。
        """
        return ConcurrentStableList(
            [
                _Series(datasource="platform", version_table=f"alembic_version_{domain}"),
                _Series(datasource="tenant", version_table=f"alembic_version_{domain}"),
            ]
        )

    monkeypatch.setattr(release_ops, "domain_series", _series_of)

    revisions = release_ops.DatabaseRevisions(ConcurrentStableDict({"platform": "sqlite+aiosqlite:///platform.db"}))
    assert await revisions.current("alpha") == "0001"
    assert await revisions.current("beta") is None

    both = release_ops.DatabaseRevisions(
        ConcurrentStableDict({"platform": "sqlite+aiosqlite:///platform.db", "tenant": "sqlite+aiosqlite:///tenant.db"})
    )
    assert await both.current("alpha") == "0001"
