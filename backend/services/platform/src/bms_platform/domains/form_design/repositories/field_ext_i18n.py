"""自建字段名多语言附表仓储（`sys_field_ext_i18n`）：批量读写经基座统一助手。

读写统一走 `bms_core/repositories/i18n.py` 的 `load_i18n_texts` / `replace_i18n_texts` /
`soft_delete_i18n`（《数据规范》§5 口径：三级回退、主表默认文案列为派生快照、同生命周期连带软删），
**不在本域自建一套多语言读写**。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.platform.form_design import SysFieldExtI18n
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.repositories.i18n import load_i18n_texts, replace_i18n_texts

__all__ = ["FieldExtI18nRepository"]


class FieldExtI18nRepository(BaseDbRepository[SysFieldExtI18n]):
    """自建字段名多语言附表仓储（薄壳：真实读写委托基座助手）。"""

    model = SysFieldExtI18n

    async def load_names(
        self,
        field_ids: ConcurrentStableList[int],
        *,
        locales: ConcurrentStableList[str],
    ) -> ConcurrentStableDict[int, str]:
        """按语言优先级批量装载字段名（三级回退由助手实现）。

        Args:
            field_ids: 自建字段主键。
            locales: 语言优先级序（从高到低）。

        Returns:
            ConcurrentStableDict[int, str]: 字段主键 → 该列优先级最高的非空文本。
        """
        buckets = await load_i18n_texts(
            self._session,
            SysFieldExtI18n,
            "field_id",
            field_ids,
            locales=locales,
        )
        names: ConcurrentStableDict[int, str] = ConcurrentStableDict()
        for field_id, columns in buckets.items():
            text = columns.get("name")
            if text is not None:  # pragma: no cover - 助手只回非空文本
                names.set(field_id, text)
        return names

    async def replace_names(self, field_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """整份覆盖某字段的多语言名（主表默认列由调用方派生写入）。

        Args:
            field_id: 自建字段主键。
            names: 语言 → 文案（内部转为助手要求的「语言 → {列名: 文案}」形态）。
        """
        texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for locale, name in names.items():
            texts.set(locale, ConcurrentStableDict({"name": name}))
        await replace_i18n_texts(self._session, SysFieldExtI18n, "field_id", field_id, texts)
