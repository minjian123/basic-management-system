"""参照拓扑模板（07C `02_01` §3.5）：三档常见组合的展开常量。

- **模板是展开用的常量，不是契约**：展开后可人工调整再写入；模板改动不影响已落库的拓扑
  （已生效的拓扑是数据，不是引用）；
- **只展开已登记业务域**：模板按传入的域集合展开，未登记的域（如 `biz` 接入前的采购 / 仓储 / 销售）
  不出现——否则「引用未登记业务域即拒」的校验会让模板自身不可用；
- **默认拓扑不使用模板**：默认拓扑必须与现状承载一致（`02_01` §3.7），模板表达的是目标形态；
- 落点与 `TopologyResolver` 同目录：写入方、`02_02` 寻址、`04_02` 迁移三方共用，不绑某一服务。
"""

from collections.abc import Iterable
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject

__all__ = [
    "DEFAULT_UNIT_KEY",
    "GROUPED_UNIT_PREFIX",
    "TEMPLATES",
    "TEMPLATE_GROUPED",
    "TEMPLATE_ISOLATED",
    "TEMPLATE_SINGLE",
    "TEMPLATE_UNIT_PREFIX",
    "TemplateRow",
    "expand_template",
]

DEFAULT_UNIT_KEY = "core"
"""单体型 / 分组型的公共单元标识（一个进程承载多个业务域）。"""

TEMPLATE_SINGLE = "single"
"""单体型：全部已登记域 → 一个单元。"""

TEMPLATE_GROUPED = "grouped"
"""分组型：平台域与组织 → 公共单元；采购 / 仓储 + 销售域登记后各自成组。"""

TEMPLATE_ISOLATED = "isolated"
"""独立型：每域一个单元（`dom-*`）。"""

TEMPLATES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (TEMPLATE_SINGLE, TEMPLATE_GROUPED, TEMPLATE_ISOLATED)
)
"""合法模板名（插入序：单体 / 分组 / 独立）。"""

TEMPLATE_UNIT_PREFIX = "dom-"
"""独立型的单元前缀（`dom-` + 域标识，下划线换连字符以符合单元命名）。"""

GROUPED_UNIT_PREFIX = "biz-"
"""分组型的产品域单元前缀（`biz-purchase` / `biz-ops`）。"""

_GROUPED_UNITS: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict(
    (
        ("purchase", f"{GROUPED_UNIT_PREFIX}purchase"),
        ("warehouse", f"{GROUPED_UNIT_PREFIX}ops"),
        ("sales", f"{GROUPED_UNIT_PREFIX}ops"),
    )
)
"""分组型的产品域归属（`domain_key 片段 → 单元`）；未登记的域不展开。"""


@dataclass(frozen=True)
class TemplateRow(BaseValueObject):
    """模板展开出的一行（写入拓扑前可人工调整）。"""

    domain_key: str
    """业务域标识。"""

    unit_key: str
    """部署单元标识。"""


def expand_template(name: str, domains: Iterable[str]) -> ConcurrentStableList[TemplateRow]:
    """按模板展开为行集合（只展开 `domains` 中出现的域，保持域声明顺序）。

    Args:
        name: 模板名（`single` / `grouped` / `isolated`）。
        domains: 已登记业务域标识集合（`domain_service_view()` 的键即可）。

    Returns:
        ConcurrentStableList[TemplateRow]: 展开结果（域插入序）。

    Raises:
        ParamError: 模板名未知（10001）。
    """
    if name not in TEMPLATES:
        raise ParamError(f"未知的拓扑模板：{name}（可选 {' / '.join(TEMPLATES)}）")
    rows: ConcurrentStableList[TemplateRow] = ConcurrentStableList()
    for domain in domains:
        rows.add(TemplateRow(domain_key=domain, unit_key=_unit_for(name, domain)))
    return rows


def _unit_for(name: str, domain: str) -> str:
    """按模板与域取部署单元标识。

    Args:
        name: 模板名。
        domain: 业务域标识（已确保在 `TEMPLATES` 内）。

    Returns:
        str: 部署单元标识。
    """
    if name == TEMPLATE_ISOLATED:
        return f"{TEMPLATE_UNIT_PREFIX}{domain.replace('_', '-')}"
    if name == TEMPLATE_GROUPED:
        for fragment, unit in _GROUPED_UNITS.items():
            if domain == fragment or domain.endswith(f"_{fragment}"):
                return unit
    return DEFAULT_UNIT_KEY
