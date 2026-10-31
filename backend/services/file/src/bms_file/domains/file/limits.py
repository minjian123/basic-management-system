"""文件域运行期参数（`file.upload.*` / `file.download.presign_ttl`）：批量读取 + 代码默认回落。

口径（《03_01 详细设计》§4.9）：

- 一次 `get_many` 批量取四键；**缺失 / 非法 / 源不可达一律回落代码默认**（上传能力不得被配置面拖死），
  解析失败只 `warning`，不抛业务错；
- 缓存由 `BaseConfigSource` 承担（02_02 版本化载荷），本层不自建缓存，保证改参数后按 TTL（≤300s）生效。
"""

from dataclasses import dataclass, field

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_file.domains.file.rules import DEFAULT_WHITELIST, WhitelistEntry, parse_whitelist

__all__ = [
    "DEFAULT_MAX_FILE_SIZE",
    "DEFAULT_MAX_UPLOAD_SIZE",
    "DEFAULT_PRESIGN_TTL",
    "MAX_FILE_SIZE_KEY",
    "MAX_UPLOAD_SIZE_KEY",
    "PRESIGN_TTL_KEY",
    "WHITELIST_KEY",
    "FileLimits",
]

_LOGGER = get_logger("bms")

MAX_UPLOAD_SIZE_KEY = "file.upload.max_size"
"""整包上传大小上限参数键（字节）。"""

MAX_FILE_SIZE_KEY = "file.upload.max_file_size"
"""单文件大小上限参数键（字节，分片上传）。"""

WHITELIST_KEY = "file.upload.whitelist"
"""类型白名单参数键（`mime:ext|ext,...`）。"""

PRESIGN_TTL_KEY = "file.download.presign_ttl"
"""预签名有效期上限参数键（秒）。"""

DEFAULT_MAX_UPLOAD_SIZE = 20 * 1024 * 1024
"""整包上传上限代码默认（20MB；与平台默认清单同值）。"""

DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
"""单文件上限代码默认（2GB；与平台默认清单同值）。"""

DEFAULT_PRESIGN_TTL = 3600
"""预签名有效期代码默认（秒）。"""


@dataclass(frozen=True)
class FileLimits(BaseValueObject):
    """文件域生效参数（已解析；白名单按需解析缓存于实例）。"""

    max_upload_size: int = DEFAULT_MAX_UPLOAD_SIZE
    """整包上传上限（字节）。"""

    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    """单文件上限（字节）。"""

    presign_ttl: int = DEFAULT_PRESIGN_TTL
    """预签名有效期上限（秒）。"""

    whitelist_raw: str = DEFAULT_WHITELIST
    """白名单原文。"""

    whitelist: ConcurrentStableDict[str, WhitelistEntry] = field(
        init=False, default_factory=lambda: ConcurrentStableDict[str, WhitelistEntry](), repr=False
    )
    """解析后的白名单（扩展名 → 条目；构造期派生，不参与外部构造）。"""

    def __post_init__(self) -> None:
        """解析白名单一次（frozen 实例经 `object.__setattr__` 写入派生字段）。"""
        object.__setattr__(self, "whitelist", parse_whitelist(self.whitelist_raw))

    @classmethod
    async def load(cls, source: BaseConfigSource | None) -> FileLimits:
        """从系统参数源加载（源为 None / 不可达 / 值非法时回落代码默认）。

        Args:
            source: 系统参数取数实现（None 表示不接线，全用代码默认）。

        Returns:
            FileLimits: 生效参数。
        """
        if source is None:
            return cls()
        keys: ConcurrentStableList[str] = ConcurrentStableList(
            (MAX_UPLOAD_SIZE_KEY, MAX_FILE_SIZE_KEY, WHITELIST_KEY, PRESIGN_TTL_KEY)
        )
        values = await source.get_many(keys)
        return cls(
            max_upload_size=_as_int(values, MAX_UPLOAD_SIZE_KEY, DEFAULT_MAX_UPLOAD_SIZE),
            max_file_size=_as_int(values, MAX_FILE_SIZE_KEY, DEFAULT_MAX_FILE_SIZE),
            presign_ttl=_as_int(values, PRESIGN_TTL_KEY, DEFAULT_PRESIGN_TTL),
            whitelist_raw=values.get(WHITELIST_KEY) or DEFAULT_WHITELIST,
        )


def _as_int(values: ConcurrentStableDict[str, str], key: str, default: int) -> int:
    """取正整数参数值（缺失 / 非法回落默认）。

    Args:
        values: 参数取值结果。
        key: 参数键。
        default: 代码默认。

    Returns:
        int: 生效值。
    """
    raw = values.get(key)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        _LOGGER.warning("文件参数值非法（回落代码默认）", key=key)
        return default
    if parsed <= 0:
        _LOGGER.warning("文件参数值非正（回落代码默认）", key=key)
        return default
    return parsed
