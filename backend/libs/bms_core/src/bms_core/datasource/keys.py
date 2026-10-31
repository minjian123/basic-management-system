"""平台内建数据源标识常量（02_01）：字典 / 表单数据源 key 的**唯一字面量落点**。

口径（`02_01` 详细设计 §4.8「key 常量集中」）：`DATA_SOURCE_CATALOG` 与 `FORM_CATALOG` 的
`data_source_key` 一律引用本枚举，业务代码只 import 常量、不写裸字符串——key 改名只改本文件与
规格表（`dict_specs.py`）两处，不会散落到几十个表单、几十个字段里。

- 枚举值须与 `DATA_SOURCE_CATALOG` 键集合**完全一致**（多一个少一个即红）：
  护栏见 `tests/datasource/test_registry_guard.py`。
- 产品（跨仓）数据源标识**不入本枚举**：由产品仓 `deploy/registry/<产品>.toml` 的 `data_sources`
  段声明、经 `register_data_source_records()` 装载（基座源码不出现产品名）。
"""

from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableFrozenList

__all__ = ["DataSourceKey", "platform_data_source_keys"]


class DataSourceKey(StrEnum):
    """平台内建数据源标识（12 个，与 `DATA_SOURCE_CATALOG` 一一对应）。"""

    ACTION = "action"
    BUSINESS = "business"
    CLIENT = "client"
    CONFIG = "config"
    ICON = "icon"
    IDENTITY_PROVIDER = "identity_provider"
    MODULE = "module"
    PRODUCT = "product"
    ROLE = "role"
    TASK = "task"
    TENANT = "tenant"
    USER = "user"


def platform_data_source_keys() -> ConcurrentStableFrozenList[str]:
    """平台内建数据源标识清单（枚举声明序，供护栏与对账使用）。

    Returns:
        ConcurrentStableFrozenList[str]: 12 个标识（不可变）。
    """
    return ConcurrentStableFrozenList[str](key.value for key in DataSourceKey)
