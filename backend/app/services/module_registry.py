"""模块注册服务：平台域固定清单与三要素（表前缀 / 错误码段 / 事件域）唯一与格式校验。

- 本阶段为**占位**：不连库，平台域固定 4 行以固定值返回；业务模块由产品仓库交付时登记。
- 真实落表、种子迁移与接库查重随落库阶段；启动校验与 CI 校验复用本服务。
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.base import BaseObject

_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*_$")
_SEGMENT_RE = re.compile(r"^\d{2}$")
_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ModuleRecord(BaseObject):
    """模块注册记录（占位数据形态，字段与 `sys_module` 对齐）。"""

    module_key: str
    name: str
    table_prefix: str
    errcode_segment: str
    event_domain: str
    status: str = "enabled"


PLATFORM_MODULES: tuple[ModuleRecord, ...] = (
    ModuleRecord("sys", "系统", "sys_", "01", "sys"),
    ModuleRecord("wf", "工作流", "wf_", "02", "wf"),
    ModuleRecord("rpt", "报表", "rpt_", "03", "rpt"),
    ModuleRecord("ai", "AI 域", "ai_", "04", "ai"),
)


def _duplicates(values: list[str]) -> list[str]:
    """取重复值（保持首次出现顺序）。

    Args:
        values: 待检查值列表。

    Returns:
        list[str]: 重复出现的值。
    """
    counter = Counter(values)
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if counter[value] > 1 and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class ModuleRegistry(BaseObject):
    """模块注册服务（占位）：清单查询与唯一性 / 格式校验。"""

    def __init__(self, modules: Sequence[ModuleRecord] = PLATFORM_MODULES) -> None:
        """初始化。

        Args:
            modules: 注册清单；默认平台域固定清单。
        """
        self._modules = list(modules)

    def list_modules(self, *, status: str | None = None) -> list[ModuleRecord]:
        """返回注册清单（可按状态筛选）。

        Args:
            status: 状态筛选（`enabled` / `disabled` / `planned`）；None 返回全部。

        Returns:
            list[ModuleRecord]: 注册记录列表。
        """
        if status is None:
            return list(self._modules)
        return [module for module in self._modules if module.status == status]

    def validate(self) -> list[str]:
        """校验注册清单：三要素唯一 + 格式。

        Returns:
            list[str]: 冲突 / 非法明细；空列表表示通过。
        """
        errors: list[str] = []
        for module in self._modules:
            if not _PREFIX_RE.match(module.table_prefix):
                errors.append(f"{module.module_key}：table_prefix 非法（{module.table_prefix}）")
            if not _SEGMENT_RE.match(module.errcode_segment) or int(module.errcode_segment) < 1:
                errors.append(f"{module.module_key}：errcode_segment 非法（{module.errcode_segment}）")
            if not _DOMAIN_RE.match(module.event_domain):
                errors.append(f"{module.module_key}：event_domain 非法（{module.event_domain}）")
        for field in ("module_key", "table_prefix", "errcode_segment", "event_domain"):
            for duplicate in _duplicates([str(getattr(module, field)) for module in self._modules]):
                errors.append(f"{field} 重复：{duplicate}")
        return errors
