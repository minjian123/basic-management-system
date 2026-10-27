"""业务域迁移清单注册：清单名 `{domain}:{datasource}`（业务域 × 数据源）→ 版本目录 / 版本记录表 / 表集 / 连接串取法。

术语（07C `03_02`，与架构 39「数据与库」节一致）：

- **表结构变更清单**（下称清单，`MigrationSeries`）：一个业务域的全部结构变更脚本，按时间顺序线性排列，
  **独立记录执行进度**；域内线性、域间互不引用。清单名即配置段名：缺省清单 `platform_registry:tenant`
  用 `[alembic]`（兼容裸命令），其余清单用 `[alembic:{domain}:{datasource}]`（如
  `[alembic:user:tenant]`），命令 `alembic -n alembic:user:tenant upgrade head`。
- **表结构变更记录表**：每清单一张，表名 `alembic_version_{domain}`（域内多数据源各自的清单在**不同库**里，
  同名不冲突；归档清单固定 `alembic_version_archive`）。表名只由域标识派生——**表是数据对象，不加数据源段**。
- **版本目录**：`alembic/versions/{domain}/{datasource}/`；`branch_labels` 取清单名；revision 编号
  **清单内唯一、清单内独立递增**（跨清单允许同名）。
- **目标表集**：`services/table_registry.py::series_tables(domain, datasource)`（仅 `status = enabled`
  且**归属本域**的表）∩ 已有模型（`Base.metadata.tables`）。基础设施表（发件箱三表）不进域清单，
  由部署单元级建表集（`unit_tables`）追加。
- **模型导入按域**：`domain_model_modules(domain)` = 承载服务的模型模块 + 公共模型模块。当前模型文件
  **文件级混域**（`models/platform/menu.py` 等各自声明 2~3 个域），故导入的是承载服务全量模型，
  实际建表集仍按域表集取交集；按域分包后收紧为逐域模块（设计 §8 对齐记录）。
- **部署单元**：`[app].unit` 可选，缺省回落 `[app].service`（2026-10-25 拍板：既有部署库名不变）。
  单元所含域由域布局声明（`deploy/boundaries/domain_layout.json`）按承载服务反推——**不另起第二套域登记**。
  单元在库维度的执行顺序 = `unit_series(unit, datasource)` 的稳定顺序（按域名），失败不回滚已成功清单。
- **连接串取法**：显式 `db_key` 优先（运维通道）；缺省按清单的数据源解析——平台库取该域**承载单元**的
  平台服务库（全限定键 `platform_{unit}`）、租户库回落 `[database.tenants].url`（真库批量迁移一律经库键）、
  归档库取 `[database.archive].url`（归档库不服务化）。
- **旧形态拒绝**（2026-10-25 拍板）：`{service}:{datasource}` 不再兼容——服务标识不是业务域，遇到即报错
  并提示改用域清单名（本仓迁移脚本已清空，无存量清单名）。
- **脚本清空（06_05）**：`alembic/versions/**` 历史迁移脚本已清空；清单注册 / 配置段映射 / 版本目录 /
  达梦方言补丁 / 库级编排机制**保留**，将来 schema 演进时按新基线重建脚本。表结构由**幂等建表**落地
  ——启动期 `db/bootstrap.py::ensure_unit_schema`、运维 / CI 显式入口 `ops/init_schema.py`
  （两处共用 `series_metadata` 表集派生点）。
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

import asyncio
import importlib
import importlib.util
import os
import re
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import compat as alembic_compat
from sqlalchemy import Connection, MetaData, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.core.paths import resolve_backend_root
from bms_core.db.keys import build_platform_db_key
from bms_core.models.base import Base
from bms_core.models.identity import MODEL_MODULES as IDENTITY_MODEL_MODULES
from bms_core.models.platform import MODEL_MODULES as PLATFORM_MODEL_MODULES
from bms_core.models.tenant import MODEL_MODULES as TENANT_MODEL_MODULES
from bms_core.services.table_registry import (
    known_service_keys,
    registered_domains,
    series_tables,
    table_ownership_view,
)


# bare-collections:allow（覆盖上游 alembic 钩子同签名实现，参数 / 返回受框架约束为内置容器）
def _read_config_parser_utf8(file_config: ConfigParser, file_argument: list[str | os.PathLike[str]]) -> list[str]:
    """以 UTF-8 读取 Alembic 配置文件的替换实现（上游默认按本地编码读）。

    Args:
        file_config: 目标配置解析器。
        file_argument: 配置文件路径列表。

    Returns:
        list[str]: 成功读取的路径列表（与上游同签名同返回）。
    """
    return file_config.read(file_argument, encoding="utf-8")


# Windows 兼容：上游 `alembic.util.compat.read_config_parser` 以 `encoding="locale"` 读配置
# （中文 Windows 为 GBK），本仓 `alembic.ini` 一律 UTF-8 且含中文注释，读取直接解码失败；此处
# 统一改写为 UTF-8 读入，使程序化迁移与直接构造 `Config` 的路径在 Windows / Linux 行为一致。
alembic_compat.read_config_parser = _read_config_parser_utf8


DATASOURCE_PLATFORM = "platform"
"""数据源段：平台服务库。"""

DATASOURCE_TENANT = "tenant"
"""数据源段：服务租户库。"""

DATASOURCE_ARCHIVE = "archive"
"""数据源段：归档库（不服务化，单清单）。"""

DATASOURCES: ConcurrentStableList[str] = ConcurrentStableList(
    (DATASOURCE_PLATFORM, DATASOURCE_TENANT, DATASOURCE_ARCHIVE)
)
"""数据源段集合（保序：平台 → 租户 → 归档）。"""

SERIES_SEPARATOR = ":"
"""清单名分隔符（清单名形如 `user:tenant`）。"""

DEFAULT_DOMAIN = "platform_registry"
"""缺省清单的业务域（平台注册与目录；`[alembic]` 段指向它，保证裸命令有明确语义）。"""

DEFAULT_SERIES_NAME = f"{DEFAULT_DOMAIN}{SERIES_SEPARATOR}{DATASOURCE_TENANT}"
"""缺省清单（`platform_registry:tenant`）：配置段 `[alembic]` 指向它。"""

CONFIG_SECTION = "alembic"
"""Alembic 缺省配置段名（其余段形如 `alembic:{domain}:{datasource}`）。"""

ARCHIVE_DOMAIN = "archive"
"""归档清单的域段占位（归档库不按域拆，单清单 `archive:archive`）。"""

ARCHIVE_SERIES_NAME = f"{ARCHIVE_DOMAIN}{SERIES_SEPARATOR}{DATASOURCE_ARCHIVE}"
"""归档清单名（`archive:archive`；表集为空，仅占位）。"""

DOMAIN_LAYOUT_RELATIVE = "deploy/boundaries/domain_layout.json"
"""域布局声明（域 → 承载服务）相对仓库根路径；镜像内缺失时按表归属登记反推。"""

_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""业务域标识形态（小写字母开头，仅小写字母、数字与下划线）。"""

COMMON_MODEL_MODULES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "bms_core.models.ownership",
        "bms_core.models.outbox",
        "bms_core.config.models",
        "bms_core.listing.models",
        *PLATFORM_MODEL_MODULES,
        *IDENTITY_MODEL_MODULES,
        *TENANT_MODEL_MODULES,
    )
)
"""**全量**共享模型模块清单（无域布局时的安全回退面；不表示「每条清单都导入」）。

- 基座自有模块四条（归属登记 / 发件箱 / 系统参数 / 查询方案）；
- 共享模型三条子包清单（14_01 整包下沉）：子包 `models/{platform,identity,tenant}::MODEL_MODULES` 是
  「有哪些共享模型」的唯一登记点，本清单只做组合；
- 有域布局时按域派生（`domain_model_modules`），本清单只在**布局缺失**（容器内未携带 `deploy/`）时兜底，
  保证建表集与分包前一致。
"""

BASE_MODEL_MODULES: ConcurrentStableList[str] = ConcurrentStableList(("bms_core.models.outbox",))
"""基座基础设施模型（发件箱三表：不归业务域、每库一份，由部署单元级建表集追加）。"""

_DOMAIN_MODEL_CACHE: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
"""域 → 模型模块缓存（布局只读一次；键为域标识）。"""

_LAYOUT_FILE_DOMAIN_CACHE: ConcurrentStableDict[str, str] = ConcurrentStableDict()
"""布局「文件 → 域」缓存（空表示尚未装载或布局缺失）。"""


SERVICE_MODEL_MODULES_ENTRY = "MODEL_MODULES"
"""服务包自声明模型模块清单的常量名（`{package_prefix}_{service}/models/__init__.py`）。"""

_SCOPE_SUFFIX: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        DATASOURCE_PLATFORM: "平台服务库",
        DATASOURCE_TENANT: "服务租户库",
        DATASOURCE_ARCHIVE: "归档库",
    }
)


def _find_backend_root() -> Path:
    """定位后端工程根（`backend/`）：经统一入口解析（环境变量优先，其次向上搜根）。

    工作区形态与依赖外置形态下，工程根位置会变（`.venv` 外置为符号链接时包体不再位于仓库内），
    故统一走 `bms_core.core.paths.resolve_backend_root`——显式覆盖优先，否则自本文件向上搜首个含
    `alembic.ini` 的目录（搜索不穿透符号链接，外置态仍能命中仓库内工程根）。

    Returns:
        Path: 后端工程根目录。

    Raises:
        ConfigError: 环境变量取值无效，或向上未找到含 `alembic.ini` 的目录（工程布局异常）。
    """
    return resolve_backend_root("alembic.ini", anchor=Path(__file__))


BACKEND_ROOT = _find_backend_root()
"""后端工程根（`backend/`）：含 `alembic.ini` 的最近祖先目录。"""

REPO_ROOT = BACKEND_ROOT.parent
"""仓库根（域布局声明等部署期文件的定位基准）。"""

VERSIONS_ROOT = BACKEND_ROOT / "alembic" / "versions"
"""迁移脚本根目录（按 `{domain}/{datasource}` 两级分子目录）。"""

_DM = "dm"
"""达梦方言名（无异步驱动，走同步引擎）。"""
_DM_DIALECTS: ConcurrentStableList[str] = ConcurrentStableList((_DM, "dmxa"))
"""达梦方言名集合（原生 `dm` 与自定义 XA 方言 `dmxa`；05_05 归一后运行期多为 `dmxa`）。"""


@dataclass(frozen=True)
class MigrationSeries(BaseValueObject):
    """迁移清单定义（业务域 × 数据源 → 版本目录 / 版本记录表 / 表集 / 分支标签）。"""

    name: str
    """清单名（`{domain}:{datasource}`，同时是配置段名与分支标签）。"""

    domain: str
    """业务域标识（清单归属域；归档清单取占位 `archive`）。"""

    datasource: str
    """数据源段（`platform` / `tenant` / `archive`）。"""

    tables: ConcurrentStableFrozenSet[str]
    """该清单目标表集（归属登记按域派生；实际建表以脚本为准）。"""

    scope: str
    """库语义说明（如「platform_registry 域的服务租户库」）。"""

    @property
    def branch(self) -> str:
        """分支标签（与清单名一致，写入迁移脚本 `branch_labels`）。

        Returns:
            str: 分支标签。
        """
        return self.name

    @property
    def version_table(self) -> str:
        """表结构变更记录表名（`alembic_version_{domain}`）。

        Returns:
            str: 版本记录表名。
        """
        return version_table_name(self.domain)

    @property
    def version_location(self) -> Path:
        """版本目录（`alembic/versions/{domain}/{datasource}/`）。

        Returns:
            Path: 版本目录路径。
        """
        return VERSIONS_ROOT / self.domain / self.datasource


def version_table_name(domain: str) -> str:
    """取清单的版本记录表名（`alembic_version_{domain}`）。

    域标识已是 snake_case（《命名规范》「大小写风格」节），可直接拼入表名，无需转义或引号。

    Args:
        domain: 业务域标识。

    Returns:
        str: 版本记录表名。
    """
    return f"alembic_version_{domain}"


def layout_domain_services() -> ConcurrentStableDict[str, str]:
    """取域 → 承载服务映射（域布局声明；声明缺失时回落表归属登记的 `owner`）。

    **单一来源**：域清单只在 `deploy/boundaries/domain_layout.json` 登记，本函数只读不另建表。

    Returns:
        ConcurrentStableDict[str, str]: 域标识到承载服务标识（声明序）。
    """
    path = REPO_ROOT / DOMAIN_LAYOUT_RELATIVE
    mapping: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if path.is_file():
        from bms_core.boundary.domains import load_layout

        mapping.update(load_layout(path).domain_services())
    for record_domain in registered_domains():
        if record_domain in mapping:
            continue
        carrier = next(
            (record.owner for record in table_ownership_view() if record.domain == record_domain),
            "",
        )
        if carrier:
            mapping.set(record_domain, carrier)
    return mapping


def known_domains() -> ConcurrentStableList[str]:
    """全部已知业务域标识（布局声明 ∪ 表归属登记，保序去重）。

    Returns:
        ConcurrentStableList[str]: 域标识列表。
    """
    return ConcurrentStableList(layout_domain_services().keys())


def domain_service(domain: str) -> str | None:
    """取域的承载服务（未登记返回 None）。

    Args:
        domain: 业务域标识。

    Returns:
        str | None: 承载服务标识。
    """
    return layout_domain_services().get(domain)


def build_series_name(domain: str, datasource: str) -> str:
    """构造清单名（`{domain}:{datasource}`）。

    Args:
        domain: 业务域标识（须已登记；归档清单用 `archive`）。
        datasource: 数据源段（`platform` / `tenant` / `archive`）。

    Returns:
        str: 清单名。

    Raises:
        ConfigError: 域标识未登记 / 形态非法，或数据源段非法。
    """
    if not domain:
        raise ConfigError("清单名需要业务域标识（形如 user:tenant）")
    if not _DOMAIN_RE.match(domain):
        raise ConfigError(f"业务域标识形态非法：{domain}（须为 snake_case，如 platform_registry）")
    if datasource not in DATASOURCES:
        raise ConfigError(f"数据源段非法：{datasource}（允许 {' / '.join(DATASOURCES)}）")
    if domain == ARCHIVE_DOMAIN and datasource != DATASOURCE_ARCHIVE:
        raise ConfigError(f"归档域占位只能配归档数据源（现 {datasource}）")
    if domain != ARCHIVE_DOMAIN and domain not in known_domains():
        raise ConfigError(f"业务域标识未登记：{domain}（见 {DOMAIN_LAYOUT_RELATIVE}）")
    return f"{domain}{SERIES_SEPARATOR}{datasource}"


def parse_series_name(name: str) -> tuple[str, str]:
    """反解清单名（`{domain}:{datasource}`）。

    **旧 `{service}:{datasource}` 形态不兼容**（2026-10-25 拍板）：服务标识不是业务域，解析失败时若
    首段命中服务标识，错误信息直接提示改用域清单名，不猜、不静默映射。

    Args:
        name: 清单名。

    Returns:
        tuple[str, str]: （业务域标识, 数据源段）。

    Raises:
        ConfigError: 清单名形态非法 / 数据源段非法 / 域标识未登记。
    """
    raw = name.strip()
    parts = raw.split(SERIES_SEPARATOR)
    if len(parts) != 2 or not all(parts):
        raise ConfigError(f"清单名形态非法：{name}（应为 {{domain}}:{{datasource}}，如 user:tenant）")
    domain, datasource = parts
    if datasource not in DATASOURCES:
        raise ConfigError(f"清单 {name} 的数据源段非法：{datasource}（允许 {' / '.join(DATASOURCES)}）")
    if domain != ARCHIVE_DOMAIN and domain not in known_domains() and domain in known_service_keys():
        raise ConfigError(
            f"清单 {name} 用的是服务标识 {domain}：清单按业务域组织，旧 {{service}}: 形态已废弃，"
            f"请改用域清单名（如已登记域见 {DOMAIN_LAYOUT_RELATIVE}）"
        )
    if domain not in known_domains() and domain != ARCHIVE_DOMAIN:
        raise ConfigError(f"清单 {name} 的业务域标识未登记：{domain}")
    return domain, datasource


def resolve_series(name: str) -> MigrationSeries:
    """按清单名取清单定义（表集由归属登记按域派生）。

    Args:
        name: 清单名（`{domain}:{datasource}`）。

    Returns:
        MigrationSeries: 清单定义。

    Raises:
        ConfigError: 清单名形态非法 / 域标识未登记。
    """
    domain, datasource = parse_series_name(name)
    scope = f"{domain} 域的{_SCOPE_SUFFIX[datasource]}"
    return MigrationSeries(
        name=f"{domain}{SERIES_SEPARATOR}{datasource}",
        domain=domain,
        datasource=datasource,
        tables=ConcurrentStableFrozenSet(series_tables(domain, datasource)),
        scope=scope,
    )


def default_series() -> MigrationSeries:
    """缺省清单（`platform_registry:tenant`，对应配置段 `[alembic]`）。

    Returns:
        MigrationSeries: 缺省清单定义。
    """
    return resolve_series(DEFAULT_SERIES_NAME)


def series_names() -> ConcurrentStableList[str]:
    """全部候选清单名（域集 × 数据源集，保序；空清单由 `has_revisions` 过滤）。

    Returns:
        ConcurrentStableList[str]: 清单名列表（域名字典序，数据源保序；归档清单在后）。
    """
    names: ConcurrentStableList[str] = ConcurrentStableList(
        f"{domain}{SERIES_SEPARATOR}{datasource}"
        for domain in sorted(known_domains())
        for datasource in (DATASOURCE_PLATFORM, DATASOURCE_TENANT)
    )
    names.add(ARCHIVE_SERIES_NAME)
    return names


def domain_series(domain: str) -> ConcurrentStableList[MigrationSeries]:
    """某业务域的各数据源清单（平台 / 租户 / 归档，启动自动建表与批量迁移用）。

    Args:
        domain: 业务域标识。

    Returns:
        ConcurrentStableList[MigrationSeries]: 清单定义列表（保序）。

    Raises:
        ConfigError: 域标识未登记。
    """
    return ConcurrentStableList(resolve_series(build_series_name(domain, datasource)) for datasource in DATASOURCES)


def unit_key(settings: Settings | None = None) -> str:
    """取当前部署单元标识（`[app].unit` 优先，缺省回落 `[app].service`）。

    Args:
        settings: 应用配置；None 取全局配置单例。

    Returns:
        str: 部署单元标识（空串表示未声明）。
    """
    resolved = settings if settings is not None else get_settings()
    return resolved.app.unit or resolved.app.service


def unit_domains(unit: str) -> ConcurrentStableList[str]:
    """取部署单元所含业务域（由域布局按承载服务反推，稳定顺序）。

    **拆分拓扑的退化形态**：单元标识若本身就是已登记的业务域（布局里没有以它为承载服务的域），
    则该单元恰好承载这一个域——这样「一域一单元」无需额外登记即可表达（合并 / 拆分两拓扑同源验算）。

    Args:
        unit: 部署单元标识（缺省形态即承载服务标识；拆分形态为域标识）。

    Returns:
        ConcurrentStableList[str]: 域标识列表（字典序，保证执行顺序可复现）。
    """
    if not unit:
        return ConcurrentStableList()
    mapping = layout_domain_services()
    carriers = sorted(domain for domain, carrier in mapping.items() if carrier == unit)
    if carriers:
        return ConcurrentStableList(carriers)
    return ConcurrentStableList([unit]) if unit in mapping else ConcurrentStableList()


def unit_series(unit: str, datasource: str) -> ConcurrentStableList[MigrationSeries]:
    """取部署单元在某库类别下要执行的清单（按域名稳定排序）。

    Args:
        unit: 部署单元标识。
        datasource: 数据源段。

    Returns:
        ConcurrentStableList[MigrationSeries]: 清单定义列表（执行序）。

    Raises:
        ConfigError: 数据源段非法。
    """
    if datasource not in DATASOURCES:
        raise ConfigError(f"数据源段非法：{datasource}（允许 {' / '.join(DATASOURCES)}）")
    return ConcurrentStableList(resolve_series(build_series_name(domain, datasource)) for domain in unit_domains(unit))


def archive_series() -> MigrationSeries:
    """归档清单（`archive:archive`；归档库不服务化、不按域拆，表集为空）。

    Returns:
        MigrationSeries: 归档清单定义。
    """
    return resolve_series(ARCHIVE_SERIES_NAME)


def config_section(series: MigrationSeries) -> str:
    """取该清单的 Alembic 配置段名（缺省清单用 `[alembic]`，其余用 `[alembic:{清单名}]`）。

    Args:
        series: 清单定义。

    Returns:
        str: 配置段名。
    """
    if series.name == DEFAULT_SERIES_NAME:
        return CONFIG_SECTION
    return f"{CONFIG_SECTION}{SERIES_SEPARATOR}{series.name}"


def resolve_series_from_section(section: str) -> MigrationSeries:
    """按 Alembic 配置段名取清单（`[alembic]` → 缺省清单；`[alembic:{清单名}]` → 对应清单）。

    单入参口径：`alembic -n alembic:{domain}:{datasource} upgrade head` 与 `ops` 程序化调用同源。

    Args:
        section: 配置段名。

    Returns:
        MigrationSeries: 清单定义。

    Raises:
        ConfigError: 配置段未登记 / 缺省清单误用全限定段名。
    """
    if section == CONFIG_SECTION:
        return default_series()
    prefix = f"{CONFIG_SECTION}{SERIES_SEPARATOR}"
    if section.startswith(prefix):
        name = section[len(prefix) :]
        series = resolve_series(name)
        if series.name == DEFAULT_SERIES_NAME:
            raise ConfigError(
                f"缺省清单（{DEFAULT_SERIES_NAME}）的配置段为 [{CONFIG_SECTION}]：请用 `-n {CONFIG_SECTION}`"
            )
        return series
    raise ConfigError(
        f"未知 Alembic 配置段：{section}（允许 {CONFIG_SECTION} / {CONFIG_SECTION}:{{domain}}:{{datasource}}）"
    )


def _package_exists(package: str) -> bool:
    """判定点分包是否可导入（父包缺失 / 命名非法 / 导入期异常一律视为不存在）。

    `importlib.util.find_spec()` 在**父包不存在**时抛 `ModuleNotFoundError`（而非返回 None），
    故此处统一收敛为布尔判定（服务包不存在属正常情形：跨仓产品服务 / 预留服务）。

    Args:
        package: 点分包名。

    Returns:
        bool: 存在为 True。
    """
    try:
        return importlib.util.find_spec(package) is not None
    except ImportError, ValueError:
        return False


def service_package(service: str, *, settings: Settings | None = None) -> str:
    """取服务包名（`{package_prefix}_{service}`；前缀等于服务标识时去重为 `{service}`）。

    平台默认前缀 `bms`（如 `bms_platform`）；产品配自有前缀（如 mdm 配 `mdm`）。**前缀与产品名相同时
    去重**（2026-10-23 拍板，与库名 `prefix == service` 去重同规则）——产品 `mdm` 的服务包即 `mdm`，
    不再出现 `mdm_mdm`；其余仓 `prefix != service` 行为不变。

    Args:
        service: 服务标识。
        settings: 应用配置；None 取全局配置单例。

    Returns:
        str: 服务包名（不含 `.models` 后缀）。
    """
    prefix = (settings or get_settings()).app.package_prefix
    return service if prefix == service else f"{prefix}_{service}"


def service_model_modules(service: str, *, settings: Settings | None = None) -> ConcurrentStableList[str]:
    """取服务包自声明的**私有**模型模块清单（服务包 / `models` 子包不存在返回空清单）。

    **宽松语义**：服务包不存在（跨仓产品服务、`planned` / 预留服务）或服务包在但无 `models` 子包
    （无私有模型，14_01 共享模型整包下沉后 platform / identity / tenant 即此形态）返回空清单——
    需要「已启用服务包缺失即失败」的调用方改用严格入口 `require_service_model_modules()`（12_04）。

    Args:
        service: 服务标识。
        settings: 应用配置；None 取全局配置单例。

    Returns:
        ConcurrentStableList[str]: 模型模块清单。

    Raises:
        ConfigError: `models` 子包存在但未声明 `MODEL_MODULES`。
    """
    package = f"{service_package(service, settings=settings)}.models"
    if not _package_exists(package):
        return ConcurrentStableList(())
    module = importlib.import_module(package)
    declared = getattr(module, SERVICE_MODEL_MODULES_ENTRY, None)
    if declared is None:
        raise ConfigError(
            f"服务包 {package} 未声明 {SERVICE_MODEL_MODULES_ENTRY}（模型模块清单；无私有模型的服务"
            "可不建 models 子包，建了就必须声明空元组）"
        )
    return ConcurrentStableList(str(name) for name in declared)


def require_service_model_modules(service: str, *, settings: Settings | None = None) -> ConcurrentStableList[str]:
    """取服务包自声明的私有模型模块清单；**服务包不存在即 `ConfigError`**（严格入口；12_04）。

    用于「服务已启用但服务工程未就位 / 前缀配错」的快速失败——免静默空清单导致迁移与开发库自动建表
    不建表。**缺失判定在服务包一级**（14_01）：服务包在、`models` 子包不在 = 本服务无私有模型，
    返回空清单而非报错（共享模型下沉后 platform / identity / tenant 即此形态）。
    由消费方显式调用（平台侧 `ops.check_tables` 对已启用服务、产品侧对本服务 / 迁移目标）；
    `service_model_modules()` 维持宽松语义（预留 / 跨仓服务返回空元组不误伤）。

    Args:
        service: 服务标识。
        settings: 应用配置；None 取全局配置单例。

    Returns:
        ConcurrentStableList[str]: 模型模块清单（无私有模型为空清单）。

    Raises:
        ConfigError: 服务包不存在（包名前缀配置错误或工程未就位）。
    """
    package = service_package(service, settings=settings)
    if not _package_exists(package):
        prefix = (settings or get_settings()).app.package_prefix
        raise ConfigError(
            f"服务包不存在：{package}（当前包名前缀 [app].package_prefix={prefix}）；"
            "请确认前缀配置与服务工程包名一致（前缀 = 产品名时去重，如 mdm 配 mdm → 包名 mdm）"
        )
    return service_model_modules(service, settings=settings)


def _layout_file_domains() -> ConcurrentStableDict[str, str]:
    """取域布局的「文件 → 域」索引（布局缺失返回空；进程内缓存一次）。

    Returns:
        ConcurrentStableDict[str, str]: 相对仓库根文件 → 域标识。
    """
    if _LAYOUT_FILE_DOMAIN_CACHE:
        return _LAYOUT_FILE_DOMAIN_CACHE
    path = REPO_ROOT / DOMAIN_LAYOUT_RELATIVE
    if not path.is_file():
        return _LAYOUT_FILE_DOMAIN_CACHE
    from bms_core.boundary.domains import load_layout

    layout = load_layout(path)
    files, _problems = layout.resolve_files(REPO_ROOT)
    _LAYOUT_FILE_DOMAIN_CACHE.update({rel: domain for rel, domain in files.items() if rel.endswith(".py")})
    return _LAYOUT_FILE_DOMAIN_CACHE


def _module_of_source(rel: str) -> str | None:
    """源文件相对路径 → 模块名（`backend/{libs,services}/<工程>/src/` 前缀剥离）。

    Args:
        rel: 相对仓库根 posix 路径。

    Returns:
        str | None: 模块名；非源码返回 None。
    """
    match = re.match(r"^backend/(?:libs|services)/[^/]+/src/(.+)$", rel)
    if not match:
        return None
    parts = match.group(1)[:-3].split("/") if match.group(1).endswith(".py") else []
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _declares_table(rel: str) -> bool:
    """文件是否声明 ORM 模型（含 `__tablename__` 赋值）。

    Args:
        rel: 相对仓库根 posix 路径。

    Returns:
        bool: 声明表返回 True。
    """
    import ast

    try:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__tablename__" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return True
    return False


def _derived_domain_models(domain: str) -> ConcurrentStableList[str] | None:
    """按域布局派生该域的模型模块（布局缺失返回 None）。

    判定口径：域布局登记的文件中**声明了 `__tablename__`** 的模块即该域模型模块。

    Args:
        domain: 业务域标识。

    Returns:
        ConcurrentStableList[str] | None: 模型模块清单；布局缺失返回 None。
    """
    cached = _DOMAIN_MODEL_CACHE.get(domain)
    if cached is not None:
        return cached
    mapping = _layout_file_domains()
    if not mapping:
        return None
    modules: ConcurrentStableList[str] = ConcurrentStableList()
    for rel, owner in mapping.items():
        if owner != domain or not _declares_table(rel):
            continue
        module = _module_of_source(rel)
        if module is not None:
            modules.add(module)
    _DOMAIN_MODEL_CACHE.set(domain, modules)
    return modules


def domain_model_modules(domain: str, *, settings: Settings | None = None) -> ConcurrentStableList[str]:
    """取该业务域的模型模块清单（按域布局派生；布局缺失时回退全量）。

    - **有布局**：该域登记文件中声明了 `__tablename__` 的模块（一域一文件，跨域模型不混入）；
    - **无布局**（容器内未携带 `deploy/`）：`COMMON_MODEL_MODULES + service_model_modules(承载服务)`，
      与分包前行为一致（安全回退，建表集不变）；
    - 域未登记 / 无承载服务：空清单。

    Args:
        domain: 业务域标识。
        settings: 应用配置；None 取全局配置单例。

    Returns:
        ConcurrentStableList[str]: 模型模块清单。
    """
    derived = _derived_domain_models(domain)
    if derived is not None:
        return derived
    service = domain_service(domain)
    if not service:
        return ConcurrentStableList(())
    modules: ConcurrentStableList[str] = ConcurrentStableList(COMMON_MODEL_MODULES)
    modules.update(service_model_modules(service, settings=settings))
    return modules


def all_model_modules(*, settings: Settings | None = None) -> ConcurrentStableList[str]:
    """全部模型模块清单（基座 + 共享子包 + 各服务自声明 + 布局派生域模型；保序去重）。

    供「按服务清点模型」的离线校验使用（声明集与导入面同源）。

    Args:
        settings: 应用配置；None 取全局配置单例。

    Returns:
        ConcurrentStableList[str]: 模型模块清单。
    """
    modules: ConcurrentStableList[str] = ConcurrentStableList(BASE_MODEL_MODULES)
    modules.update(COMMON_MODEL_MODULES)
    for service in known_service_keys():
        modules.update(service_model_modules(service, settings=settings))
    for domain in _layout_file_domains().values():
        modules.update(_derived_domain_models(domain) or ())
    return modules


def import_models(domain: str) -> None:
    """导入该清单域的模型模块（注册 `Base.metadata`；幂等）。

    基座基础设施模型（发件箱）恒导入；业务域模型按布局派生（见 `domain_model_modules`）。

    Args:
        domain: 业务域标识。

    Raises:
        ConfigError: 承载服务包存在但未声明 `MODEL_MODULES`（无布局回退路径）。
    """
    for module in (*BASE_MODEL_MODULES, *domain_model_modules(domain)):
        importlib.import_module(module)


def import_service_models(service: str) -> None:
    """导入某服务的全部模型模块（离线校验按服务清点模型时用；与域清单导入同源）。

    有布局：基座基础设施模型 + 该服务承载域的全部模型模块；无布局：基座公共 + 服务自声明模型。

    Args:
        service: 服务标识。

    Raises:
        ConfigError: 服务包存在但未声明 `MODEL_MODULES`。
    """
    mapping = _layout_file_domains()
    modules: ConcurrentStableList[str] = ConcurrentStableList(BASE_MODEL_MODULES)
    if mapping:
        for domain, carrier in layout_domain_services().items():
            if carrier != service:
                continue
            modules.update(_derived_domain_models(domain) or ())
    else:
        modules.update(COMMON_MODEL_MODULES)
    modules.update(service_model_modules(service))
    for module in modules:
        importlib.import_module(module)


def series_metadata(series: MigrationSeries) -> MetaData:
    """取该清单的元数据子集（表集派生 ∩ 已有模型；沿用 `Base.metadata` 命名约定）。

    Args:
        series: 清单定义。

    Returns:
        MetaData: 元数据子集（迁移目标 / 自动建表共用）。
    """
    import_models(series.domain)
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    for name in sorted(series.tables & set(Base.metadata.tables)):
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata


def series_url(
    series: MigrationSeries,
    settings: Settings | None = None,
    *,
    db_key: str | None = None,
    allow_cross_service: bool = False,
) -> str:
    """取该清单的连接串（含分字段密码；禁止写入日志）。

    显式 `db_key` 时一律经库键与 `url_template` 解析（运维通道）；未传时按清单的数据源解析：
    平台库取该域**承载单元**的平台服务库（全限定键 `platform_{unit}`）、租户库回落
    `[database.tenants].url`（真库批量迁移一律经库键）、归档库取 `[database.archive].url`。

    Args:
        series: 清单定义。
        settings: 应用配置；None 取全局配置单例。
        db_key: 库键（`platform` / `platform_{unit}` / `tenant_{code}` / `tenant_{unit}_{code}`）。
        allow_cross_service: 是否允许跨单元库键（**仅 `ops` / 迁移运维通道**）。

    Returns:
        str: 连接串（含密码）。
    """
    resolved = settings if settings is not None else get_settings()
    if db_key:
        from bms_core.db.engine import EngineFactory

        return EngineFactory(resolved, allow_cross_service=allow_cross_service).resolved_url(db_key)
    database = resolved.database
    if series.datasource == DATASOURCE_ARCHIVE:
        return database.apply_sqlite_dir(database.archive.resolved_url())
    if series.datasource == DATASOURCE_PLATFORM:
        from bms_core.db.engine import EngineFactory

        # 库随部署单元：清单所属域的承载单元即该平台库的归属单元（运维通道，不受运行服务限制）
        unit = unit_key(resolved) or domain_service(series.domain) or series.domain
        key = build_platform_db_key(unit)
        return EngineFactory(resolved, allow_cross_service=True).resolved_url(key)
    return database.apply_sqlite_dir(database.tenants.resolved_url())


def has_revisions(series: MigrationSeries) -> bool:
    """该清单是否已有迁移脚本（空清单提示与跳过用）。

    Args:
        series: 清单定义。

    Returns:
        bool: 存在迁移脚本 True。
    """
    location = series.version_location
    if not location.is_dir():
        return False
    return any(path.suffix == ".py" for path in location.iterdir())


def alembic_config(series: MigrationSeries) -> Config:
    """取该清单的 Alembic 配置（**配置段名由清单名派生**，版本目录由配置段声明）。

    Alembic 在 `env.py` 执行**之前**读取 `version_locations`，故选清单只能经配置段；本函数是
    ops 侧程序化调用的唯一入口，配置段缺失（新增域首次迁移未补段）即快速失败。

    Args:
        series: 清单定义。

    Returns:
        Config: 该清单的 Alembic 配置。

    Raises:
        ConfigError: 该清单未在 `alembic.ini` 登记配置段（缺 `version_locations`）。
    """
    section = config_section(series)
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"), ini_section=section)
        locations = config.get_main_option("version_locations")
    except Exception as exc:  # 配置段缺失 / 读取异常一律快速失败
        raise ConfigError(f"迁移清单 {series.name} 的配置段 [{section}] 不可读：{exc}") from exc
    if not locations:
        raise ConfigError(
            f"迁移清单 {series.name} 未在 alembic.ini 登记配置段 [{section}]（缺 version_locations）；"
            "新增域首次迁移时须补段"
        )
    return config


def validate_series_registry() -> ConcurrentStableList[str]:
    """校验**迁移清单注册完整性**（07B `02_03`）：域布局里的域是否都已在 `alembic.ini` 登记。

    **为什么需要**：`alembic_config()` 只在「真要跑迁移时」才校验配置段，新增业务域忘登记
    要等到执行期才炸。本函数把这条校验前移到装载期 / CI 门禁，与其余装载校验同源。

    校验范围：`series_names()` 枚举的候选清单中**已有脚本的那些**（`has_revisions` 为真）。

    **为什么只查有脚本的**：当前阶段迁移脚本已清空（`06_05`），空清单不需要配置段——
    `alembic upgrade head` 对空清单直接「无脚本（跳过）」。只有真加了脚本的清单才必须登记，
    否则 `alembic_config()` 会在执行期抛 `ConfigError`。本校验把这条前移到装载期。

    Returns:
        ConcurrentStableList[str]: 错误明细（空列表表示全部已登记）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for name in series_names():
        try:
            series = resolve_series(name)
        except ConfigError as exc:
            errors.add(f"迁移清单 {name} 解析失败：{exc}")
            continue
        if not has_revisions(series):
            continue
        try:
            alembic_config(series)
        except ConfigError as exc:
            errors.add(str(exc))
    return errors


def head_revision(series: MigrationSeries) -> str | None:
    """取该清单 head 版本号（空清单返回 None；供「已是最新」幂等判定）。

    Args:
        series: 清单定义。

    Returns:
        str | None: head 版本号；无脚本返回 None。
    """
    if not has_revisions(series):
        return None
    return ScriptDirectory.from_config(alembic_config(series)).get_current_head()


def upgrade_series(series: MigrationSeries, url: str, *, schema: str = "") -> None:
    """**阻塞**把该清单迁移到 head（调用方用 `asyncio.to_thread` 包装）。

    连接串经 `-x url=` 显式传入（优先于配置与环境变量）；达梦模式经 `-x schema=` 切换
    （其他方言忽略该参数）。版本记录表由 `alembic/env.py` 按清单显式设置。

    Args:
        series: 清单定义。
        url: 目标连接串（含密码；禁止写入日志）。
        schema: 达梦目标模式名（空串表示不切换）。
    """
    config = alembic_config(series)
    x_args = [f"url={url}"] + ([f"schema={schema}"] if schema else [])
    config.cmd_opts = SimpleNamespace(x=x_args)  # pyright: ignore[reportAttributeAccessIssue]
    command.upgrade(config, "head")


def apply_session_schema(connection: Connection, schema: str) -> None:
    """切换达梦会话当前模式（非达梦方言 / 未指定模式时为空操作）。

    迁移与版本读取共用：达梦以**模式**为库级隔离单位，操作前须把会话切到目标模式；
    `SET SCHEMA` 不被支持时回落标准 SQL `ALTER SESSION SET CURRENT_SCHEMA`。

    Args:
        connection: 数据库连接（同步）。
        schema: 目标模式名（空串表示不切换）。
    """
    if not schema or connection.dialect.name not in _DM_DIALECTS:
        return
    try:
        connection.exec_driver_sql(f"SET SCHEMA {schema}")
    except Exception:  # 达梦版本差异：`SET SCHEMA` 不支持时回落标准 SQL 语法
        connection.exec_driver_sql(f"ALTER SESSION SET CURRENT_SCHEMA {schema}")
    # 结束 `SET SCHEMA` 打开的隐式事务：否则 Alembic 会把其视为「外部事务」而不再提交，
    # 导致迁移的版本行随连接关闭回滚（实测：表已建、版本行为空）
    if connection.in_transaction():
        connection.commit()


def _read_revision(url: str, schema: str, version_table: str) -> str | None:
    """同步读目标库该清单的版本记录表当前版本（达梦等无异步方言驱动）。

    Args:
        url: 连接串。
        schema: 目标模式名（达梦；空串表示不切换）。
        version_table: 版本记录表名（`alembic_version_{domain}`）。

    Returns:
        str | None: 当前版本号；未迁移（表不存在）返回 None。
    """
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            try:
                row = connection.exec_driver_sql(f"SELECT version_num FROM {version_table}").first()
            except ProgrammingError, OperationalError, DatabaseError:
                # 未迁移：无该版本记录表（各库异常类不同——PG / MySQL 报 ProgrammingError、
                # SQLite 报 OperationalError、达梦把「无效的表或视图名」报为 DatabaseError）
                return None
            return None if row is None else str(row[0])
    finally:
        engine.dispose()


async def current_revision(url: str, *, version_table: str, schema: str = "") -> str | None:
    """读目标库该清单的版本记录表当前版本（未迁移返回 None）。

    供 `ops` 批量迁移判断「已是最新（跳过）」与初始化报告；达梦走同步驱动线程。

    Args:
        url: 连接串。
        version_table: 版本记录表名（`alembic_version_{domain}`）。
        schema: 目标模式名（达梦；空串表示不切换）。

    Returns:
        str | None: 当前版本号；未迁移返回 None。
    """
    if make_url(url).get_backend_name() in _DM_DIALECTS:
        return await asyncio.to_thread(_read_revision, url, schema, version_table)
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            try:
                result = await connection.exec_driver_sql(f"SELECT version_num FROM {version_table}")
            except ProgrammingError, OperationalError, DatabaseError:
                return None
            value = result.scalar()
            return None if value is None else str(value)
    finally:
        await engine.dispose()
