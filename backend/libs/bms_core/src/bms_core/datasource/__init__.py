"""统一数据源泛化层：登记表 + 通用数据接口三层（02_10）。"""

from bms_core.datasource.base import (
    DATA_SOURCE_CACHE_DOMAIN,
    BaseDictDataSource,
    BaseFormDataSource,
    BaseGenericDataSource,
    DataSourceItem,
)
from bms_core.datasource.registry import (
    DATA_SOURCE_CATALOG,
    DATA_SOURCE_KEY_PATTERN,
    DataSourceKind,
    DataSourceOrigin,
    DataSourceRecord,
    DataSourceRegistry,
    DataSourceStatus,
    DataSourceStrategy,
    data_source_records_view,
    merge_data_source_records,
    register_data_source_records,
)

__all__ = [
    "DATA_SOURCE_CACHE_DOMAIN",
    "DATA_SOURCE_CATALOG",
    "DATA_SOURCE_KEY_PATTERN",
    "BaseDictDataSource",
    "BaseFormDataSource",
    "BaseGenericDataSource",
    "DataSourceItem",
    "DataSourceKind",
    "DataSourceOrigin",
    "DataSourceRecord",
    "DataSourceRegistry",
    "DataSourceStatus",
    "DataSourceStrategy",
    "data_source_records_view",
    "merge_data_source_records",
    "register_data_source_records",
]
