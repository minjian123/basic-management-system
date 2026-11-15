"""选项集 → 公开契约派生：静态值域按装载清单输出 `x-extensible-enum` / `enum`。

口径（需求 09-4 / 任务 09-03-1）：
- 静态值域的唯一来源是 `deploy/registry/<仓>.toml` 的 `[[option_sets]]`，装载时注册；
- 字段以 `optionSetKey` 标记引用（不写值），契约导出按选项集生成同名组件并写值域；
- 值域键按 `extensible` 取：闭集 `enum`（加值即破坏性变更）/ 可增长 `x-extensible-enum`；
- 不做值域一致性 / 形状护栏（选项集注册表在装载期已做冲突校验）。

**契约文档是 FastAPI 产出的 JSON 树**（`dict` / `list` 普通容器）：这里就地改写，不往文档里注入
自定义集合类型——契约快照渲染时由 `normalize_collections` 统一规整，口径与 `services/service_contract.py`
一致（那边只读，故用插入序集合承接；这边要保真回写，故按 JSON 原生结构处理）。
"""

from collections.abc import Iterable, Mapping
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.optionset.base import BaseOptionSet

__all__ = ["apply_option_set_contracts"]


def _collect_marked(node: object, marked: ConcurrentStableList[object]) -> None:
    """收集带 `optionSetKey` 标记的 schema 节点（递归对象 / 数组）。

    Args:
        node: 当前节点。
        marked: 收集结果（就地追加）。
    """
    if isinstance(node, dict):
        mapping = cast("dict[str, object]", node)
        if isinstance(mapping.get("optionSetKey"), str):
            marked.add(mapping)
        for value in mapping.values():
            _collect_marked(value, marked)
    elif isinstance(node, list):
        for item in cast("list[object]", node):
            _collect_marked(item, marked)


def apply_option_set_contracts(openapi: object, option_sets: Iterable[BaseOptionSet]) -> None:
    """按选项集改写公开契约（就地修改）。

    Args:
        openapi: 公开契约根节点（`app.openapi()` 产物）。
        option_sets: 应用级选项集清单（平台清单 + 产品清单）。
    """
    if not isinstance(openapi, Mapping):
        return
    components = cast("Mapping[object, object]", openapi).get("components")
    if not isinstance(components, Mapping):
        return
    raw_schemas = cast("Mapping[object, object]", components).get("schemas")
    if not isinstance(raw_schemas, dict):
        return
    section = cast("dict[str, object]", raw_schemas)

    by_key = {option_set.key: option_set for option_set in option_sets}
    marked: ConcurrentStableList[object] = ConcurrentStableList()
    _collect_marked(section, marked)

    for item in marked:
        node = cast("dict[str, object]", item)
        key = cast("str", node.pop("optionSetKey"))
        option_set = by_key.get(key)
        if option_set is None:
            continue
        values = [option.value for option in option_set.items()]
        domain_key = "x-extensible-enum" if option_set.extensible else "enum"
        name = option_set.contract_name
        if not name:
            node[domain_key] = values
            continue
        component = cast("dict[str, object]", {"type": "string", "title": name})
        component[domain_key] = values
        section[name] = component
        description = node.get("description")
        node.clear()
        node["$ref"] = f"#/components/schemas/{name}"
        if description is not None:
            node["description"] = description
