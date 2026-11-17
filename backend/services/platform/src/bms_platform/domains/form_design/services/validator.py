"""表单动态校验真实实现（`local` 提供者）：按生效布局 / 属性校验字段值（10_01）。

**为什么落在服务侧**：真实实现要读**租户库**的布局 / 属性表，而基座 `bms_core/formdesign/validator.py`
只承载契约与占位实现（基座不依赖任何服务，也不持有租户会话）——与 `fieldtype` / `help_content`
的分工同构：基座给端口，服务给实现，装配面注入。

**校验口径**（与前端一致）：

| 规则 | 判定 | 跳过条件 |
| --- | --- | --- |
| `type` | 值类型与字段类型匹配 | 值为空（必填另判） |
| `required` | 缺键 / `None` / 空串 / 空数组视为未填 | `editable=false` 的字段（写时由权限侧拒绝） |
| `length` | 字符串 / 数组长度在 `[min, max]` | 值为空 |
| `range` | 数值在 `[min, max]` | 值为空 / 非数值 |
| `pattern` | 正则全匹配 | 值为空 / 非字符串 |
| `options` | 值在选项集取值内（多选逐项） | 值为空 |

失败项落 `FieldError`（`field_key` + `rule`）；文案由前端按 `rule` 取词，后端不拼中文。
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.db.session import DbSession
from bms_core.formdesign.attrs import FieldAttrs, compile_rules
from bms_core.formdesign.layout import FormLayout
from bms_core.formdesign.validator import (
    BaseFormValidator,
    FieldError,
    ValidationResult,
)
from bms_core.models.platform.form_design import (
    SysFieldExt,
    SysFormFieldAttr,
)
from bms_core.permission.field import BaseFieldPermissionProvider
from bms_platform.domains.form_design.ports import FormMetadataPort, OptionSetPort
from bms_platform.domains.form_design.repositories.layout import (
    FieldAttrRepository,
    FieldExtRepository,
    FormLayoutRepository,
)
from bms_platform.domains.form_design.services.assemble import (
    LevelSnapshot,
    assemble_layout,
    collect_levels,
    pick_role_level,
)

__all__ = ["LocalFormValidator"]

_KIND_TEXT_TYPES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("text", "longtext", "option", "file"))
"""按字符串校验的类型（`option` 也是字符串常量）。"""


def _is_empty(value: object) -> bool:
    """是否视为「未填」（缺键 / None / 空串 / 空数组）。

    Args:
        value: 字段值。

    Returns:
        bool: 空为 True。
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list | tuple | set | frozenset):
        return len(cast("Collection[object]", value)) == 0
    return False


class LocalFormValidator(BaseFormValidator):
    """按生效布局 / 属性校验字段值（插件名 `local`）。"""

    plugin_name: str = "local"
    r"""实现名（插件注册键；与配置 \`[form_validator].provider = "local"\` 对应）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        layouts: FormLayoutRepository,
        attrs: FieldAttrRepository,
        ext_fields: FieldExtRepository,
        metadata: FormMetadataPort,
        option_sets: OptionSetPort,
        field_permissions: BaseFieldPermissionProvider | None = None,
        role_types: ConcurrentStableList[tuple[str, int]] | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 请求级会话（租户库）。
            layouts: 布局仓储。
            attrs: 字段属性仓储。
            ext_fields: 自建字段仓储。
            metadata: 平台库表单元数据读面。
            option_sets: 选项集读面。
            field_permissions: 字段权限求值器（None 表示不叠加：全开）。
            role_types: 当前用户角色集（`(role_type, role_id)`）；None / 空表示无角色视图。
        """
        self._session = session
        self._layouts = layouts
        self._attrs = attrs
        self._ext_fields = ext_fields
        self._metadata = metadata
        self._option_sets = option_sets
        self._field_permissions = field_permissions
        self._role_types = role_types if role_types is not None else ConcurrentStableList()

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 说明文本。
        """
        return "表单动态校验真实实现（按生效布局 / 属性）"

    async def validate(
        self,
        form_code: str,
        values: ConcurrentStableDict[str, object],
        *,
        locale: str | None = None,
        skip_required_keys: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(),  # noqa: B008 - 契约签名
    ) -> ValidationResult:
        """按生效布局与属性校验字段值。

        Args:
            form_code: 表单标识（业务码）。
            values: 待校验值（字段键 → 值）。
            locale: 当前语言（选项集标签回退用；None 表示不取）。
            skip_required_keys: 跳过必填校验的字段键。

        Returns:
            ValidationResult: 校验结果（字段级错误清单）。
        """
        del locale
        snapshot = await self._metadata.load(form_code)
        if snapshot is None:
            return ValidationResult()
        layouts = await self._layouts.list_by_form(form_code)
        attr_rows = await self._attrs.list_by_form(form_code)
        ext_fields = await self._ext_fields.list_active(form_code)
        if len(layouts) == 0 and len(attr_rows) == 0:
            # 无任何布局 / 属性配置：完全放行（与原接口行为一致，不破坏既有模块）
            return ValidationResult()
        levels = collect_levels(layouts=layouts, attr_rows=attr_rows)
        role_map = levels.get("role") or ConcurrentStableDict()
        candidates: ConcurrentStableList[tuple[str, int, FormLayout | None]] = ConcurrentStableList()
        for role_type, role_id in self._role_types:
            candidate = role_map.get(role_id)
            candidates.add((role_type, role_id, candidate.layout if candidate is not None else None))
        role_id, role_layout = pick_role_level(candidates=candidates)
        hidden, uneditable = await self._narrow(snapshot.form_id)
        platform_fields: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
            ConcurrentStableDict(
                {
                    "key": field.field_key,
                    "label": field.name,
                    "type": field.type,
                    "group": "platform",
                    "sort": field.sort,
                    "status": "active" if field.status == "enabled" else "disabled",
                    "disabled": field.status != "enabled",
                }
            )
            for field in snapshot.fields
        )
        assembled = assemble_layout(
            levels=levels,
            level="role",
            role_hint=(role_id, role_layout),
            platform_fields=platform_fields,
            ext_fields=ext_fields,
            hidden_keys=hidden,
            permissions=ConcurrentStableDict(),
            option_sets=ConcurrentStableFrozenList(),
        )
        attrs_index = self._attrs_of(attr_rows, role_id=role_id, levels=levels)
        ext_index: ConcurrentStableDict[str, SysFieldExt] = ConcurrentStableDict()
        for row in ext_fields:
            ext_index.set(row.field_key, row)
        skip = set(skip_required_keys) | set(uneditable)
        errors: ConcurrentStableList[FieldError] = ConcurrentStableList()
        for item in assembled.fields:
            key = str(item.get("key"))
            field_type = str(item.get("type"))
            attrs = attrs_index.get(key) or FieldAttrs()
            value = values.get(key)
            errors.extend(
                self._check_field(
                    field_key=key,
                    field_type=field_type,
                    attrs=attrs,
                    value=value,
                    skip_required=key in skip,
                    ext_field=ext_index.get(key),
                )
            )
        return ValidationResult(errors=ConcurrentStableFrozenList(errors))

    async def _narrow(self, form_id: int) -> tuple[ConcurrentStableFrozenList[str], ConcurrentStableFrozenList[str]]:
        """取不可见 / 不可编辑字段键（字段权限叠加）。

        Args:
            form_id: 表单主键。

        Returns:
            tuple: （不可见键, 不可编辑键）。
        """
        hidden: ConcurrentStableList[str] = ConcurrentStableList()
        uneditable: ConcurrentStableList[str] = ConcurrentStableList()
        if self._field_permissions is None or len(self._role_types) == 0:  # pragma: no cover - 恒有权限工厂与角色
            return ConcurrentStableFrozenList(hidden), ConcurrentStableFrozenList(uneditable)
        narrowing = await self._field_permissions.resolve(
            role_ids=ConcurrentStableSet(role_id for _role_type, role_id in self._role_types),
            form_ids=ConcurrentStableSet((form_id,)),
        )
        for item in narrowing:
            if not item.visible:
                hidden.add(item.field_key)
            if not item.editable:
                uneditable.add(item.field_key)
        return ConcurrentStableFrozenList(hidden), ConcurrentStableFrozenList(uneditable)

    def _attrs_of(
        self,
        attr_rows: ConcurrentStableList[SysFormFieldAttr],
        *,
        role_id: int | None,
        levels: ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]],
    ) -> ConcurrentStableDict[str, FieldAttrs]:
        """取生效层级的属性索引（与布局同层同源）。

        Args:
            attr_rows: 属性行（未用，保留以显式表达数据来源）。
            role_id: 命中角色 ID（None 表示未命中角色层）。
            levels: 层级归集。

        Returns:
            ConcurrentStableDict[str, FieldAttrs]: 字段键 → 属性。
        """
        del attr_rows
        order: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList()
        if role_id is not None:
            order.add(("role", role_id))
        order.add(("tenant", 0))
        order.add(("platform", 0))
        for scope, rid in order:
            scope_map = levels.get(scope) or ConcurrentStableDict()
            snapshot = scope_map.get(rid)
            if snapshot is not None and snapshot.layout is not None:
                return snapshot.attrs
        for scope, rid in order:
            scope_map = levels.get(scope) or ConcurrentStableDict()
            snapshot = scope_map.get(rid)
            if snapshot is not None:
                return snapshot.attrs
        return ConcurrentStableDict()  # pragma: no cover - 需「有布局但无任一层级属性」，与上轮同值

    def _check_field(
        self,
        *,
        field_key: str,
        field_type: str,
        attrs: FieldAttrs,
        value: object,
        skip_required: bool,
        ext_field: SysFieldExt | None,
    ) -> ConcurrentStableList[FieldError]:
        """校验单字段（类型 → 必填 → 长度 / 范围 / 正则 / 选项集）。

        Args:
            field_key: 字段键。
            field_type: 字段类型。
            attrs: 字段属性。
            value: 字段值。
            skip_required: 是否跳过必填（`editable=false`）。
            ext_field: 自建字段行（取选项集标识；平台字段为 None）。

        Returns:
            ConcurrentStableList[FieldError]: 该字段的错误（空表示通过）。
        """
        errors: ConcurrentStableList[FieldError] = ConcurrentStableList()
        empty = _is_empty(value)
        if not empty and not self._type_ok(field_type, value):
            errors.add(FieldError(field_key=field_key, rule="type"))
            return errors
        for rule in compile_rules(attrs, field_type):
            if rule.kind == "required":
                if not skip_required and empty:
                    errors.add(FieldError(field_key=field_key, rule="required"))
                continue
            if empty:
                continue
            if rule.kind == "length":
                if not self._length_ok(value, rule.min, rule.max):
                    errors.add(FieldError(field_key=field_key, rule="length"))
            elif rule.kind == "range":
                if not self._range_ok(value, rule.min, rule.max):
                    errors.add(FieldError(field_key=field_key, rule="range"))
            elif rule.kind == "pattern":
                if not self._pattern_ok(value, rule.pattern):
                    errors.add(FieldError(field_key=field_key, rule="pattern"))
            elif rule.kind == "options" and not self._options_ok(value, field_type, ext_field, attrs):
                errors.add(FieldError(field_key=field_key, rule="options"))
        return errors

    def _type_ok(self, field_type: str, value: object) -> bool:
        """值类型是否匹配字段类型。

        Args:
            field_type: 字段类型。
            value: 字段值。

        Returns:
            bool: 匹配为 True。
        """
        if field_type in _KIND_TEXT_TYPES:
            return isinstance(value, str)
        if field_type == "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        if field_type == "switch":
            return isinstance(value, bool)
        if field_type == "option_multi":
            if not isinstance(value, list):
                return False
            return all(isinstance(item, str) for item in cast("list[object]", value))
        return True

    def _length_ok(self, value: object, minimum: float | None, maximum: float | None) -> bool:
        """长度规则判定（字符串按码点、数组按元素数）。

        Args:
            value: 字段值。
            minimum: 下限。
            maximum: 上限。

        Returns:
            bool: 通过为 True。
        """
        size: int
        if isinstance(value, str | list | tuple):
            size = len(cast("Collection[object]", value))
        else:
            return True
        if minimum is not None and size < minimum:
            return False
        return not (maximum is not None and size > maximum)

    def _range_ok(self, value: object, minimum: float | None, maximum: float | None) -> bool:
        """数值范围判定（非数值放行，由类型规则负责）。

        Args:
            value: 字段值。
            minimum: 下限。
            maximum: 上限。

        Returns:
            bool: 通过为 True。
        """
        if isinstance(value, bool) or not isinstance(value, int | float):
            return True
        number = float(value)
        if minimum is not None and number < minimum:
            return False
        return not (maximum is not None and number > maximum)

    def _pattern_ok(self, value: object, pattern: str | None) -> bool:
        """正则全匹配判定。

        Args:
            value: 字段值。
            pattern: 正则源码。

        Returns:
            bool: 匹配（或无可判定条件）为 True。
        """
        if pattern is None or not isinstance(value, str):
            return True
        try:
            compiled = re.compile(pattern)
        except re.error:  # pragma: no cover - 保存期已校验
            return True
        return compiled.fullmatch(value) is not None

    def _options_ok(
        self,
        value: object,
        field_type: str,
        ext_field: SysFieldExt | None,
        attrs: FieldAttrs,
    ) -> bool:
        """选项集值域判定（单选 / 多选）。

        Args:
            value: 字段值。
            field_type: 字段类型。
            ext_field: 自建字段行（取 `option_set_key`）。
            attrs: 字段属性（取 `option_set_key`）。

        Returns:
            bool: 在值域内（或无法判定）为 True。
        """
        key = ext_field.option_set_key if ext_field is not None else attrs.option_set_key
        if key is None or not self._option_sets.is_registered(key):
            return True
        allowed = {str(item.get("value")) for item in self._option_sets.resolve_items(key)}
        if field_type == "option_multi":
            if not isinstance(value, list):  # pragma: no cover - 非数组已在类型规则拦截
                return False
            return all(isinstance(item, str) and item in allowed for item in cast("list[object]", value))
        return isinstance(value, str) and value in allowed
