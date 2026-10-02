"""导入导出能力域 · 导出脱敏：按「列名 → 策略」对导出行逐行逐列掩码。

- `mask_rows`：导出路径的公共脱敏工具——口径为「脱敏在传入 `BaseExporter.export` 之前完成，导出契约
  不内置脱敏」，调用方取数后、导出前调用本函数即可；掩码器经参数传入（复用请求期实例与 `data:plain` 判定）。
- 列策略由调用方给出（`{列名: 策略名}`，与 `BaseSchema.masked_fields` 映射写法同形态）；未声明列原样。
- 导出大文件记录审计的消费方口径登记于阶段计划「后续阶段待办」（真实审计基座归阶段八）。
"""

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.masking.base import BaseMasker

__all__ = [
    "mask_rows",
]


def mask_rows(
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
    fields: ConcurrentStableDict[str, str],
    masker: BaseMasker,
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """按「列名 → 策略」对导出行逐行逐列掩码（未声明列原样）。

    Args:
        rows: 导出行（列字典序列）。
        fields: 需掩码的列 → 策略映射；空映射时原样返回入参。
        masker: 掩码器（请求期经 `get_masker` 取用；持 `data:plain` 时按权限放行明文）。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 掩码后的行序列（新对象，不改入参）。
    """
    if not fields:
        return rows
    return ConcurrentStableList[ConcurrentStableDict[str, object]](
        ConcurrentStableDict[str, object](
            {
                key: masker.mask(key, value, strategy=fields[key]) if key in fields else value
                for key, value in row.items()
            }
        )
        for row in rows
    )
