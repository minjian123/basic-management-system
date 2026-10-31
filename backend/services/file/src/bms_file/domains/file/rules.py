"""文件域规则（纯函数，无 IO）：扩展名 / 嗅探 / 白名单 / 对象 key / 预览判定。

口径（《03_01 详细设计》§4.5）：

- **双校验**：扩展名必须在白名单内，且**内容嗅探**类别必须与扩展名相容（阻改扩展名绕过）；
  落库 MIME 取白名单里该扩展名对应的规范 MIME，**不采信客户端声明**。
- 嗅探只看**头部字节**（整包为完整内容前 512 字节；分片为首片前 512 字节），OOXML 只判 ZIP 容器
  （容器内目录复核需整份读取，代价不成比例，登记为已知限制）。
- 对象 key：`{tenant_code}/files/{yyyy}/{mm}/{file_id}`（无扩展名后缀，MIME 走元数据）。
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from bms_core.config.seed import DEFAULT_FILE_WHITELIST
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_core.core.objects import BaseValueObject

__all__ = [
    "DEFAULT_WHITELIST",
    "SNIFF_LENGTH",
    "WhitelistEntry",
    "extension_of",
    "is_previewable",
    "normalize_extension",
    "object_key_for",
    "parse_whitelist",
    "resolve_mime",
]

SNIFF_LENGTH = 512
"""嗅探读取的头部字节数。"""

DEFAULT_WHITELIST = DEFAULT_FILE_WHITELIST
"""白名单缺省值（与 `PLATFORM_CONFIG_DEFAULTS` 的 `file.upload.whitelist` 同源；代码默认回落）。"""

ZIP_MIME = "application/zip"
"""ZIP 容器嗅探结果（OOXML 三类的实际容器类型）。"""

TEXT_MIME = "text/plain"
"""纯文本嗅探结果。"""

_PREVIEW_PREFIX = "image/"
"""可直接预览的 MIME 前缀（图片）。"""

_PREVIEW_EXTRA = "application/pdf"
"""可直接预览的额外 MIME（PDF）。"""

_EXT_PATTERN = re.compile(r"^[a-z0-9]{1,16}$")
"""扩展名形态（小写字母数字，最长 16）。"""

_OOXML_EXTENSIONS = frozenset({"docx", "xlsx", "pptx"})
"""OOXML 三类的扩展名（容器为 ZIP）。"""

_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")
_JPEG_MAGIC = bytes.fromhex("ffd8ff")
_GIF_MAGICS = (b"GIF87a", b"GIF89a")
_ZIP_MAGIC = bytes.fromhex("504b0304")
"""各类文件头的 magic（避免源码里的裸转义序列影响可读性）。"""


@dataclass(frozen=True)
class WhitelistEntry(BaseValueObject):
    """白名单单条（一个规范 MIME 对应一组扩展名）。"""

    mime: str
    """规范 MIME（落库值）。"""

    extensions: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList[str]())
    """允许的扩展名清单（小写、无点；插入序去重）。"""


def parse_whitelist(raw: str) -> ConcurrentStableDict[str, WhitelistEntry]:
    """解析白名单文本为「扩展名 → 白名单条目」（非法条目跳过）。

    Args:
        raw: `mime:ext1|ext2,mime:ext,...` 形态文本。

    Returns:
        ConcurrentStableDict[str, WhitelistEntry]: 扩展名 → 条目。
    """
    mapping: ConcurrentStableDict[str, WhitelistEntry] = ConcurrentStableDict()
    for item in raw.split(","):
        chunk = item.strip()
        if not chunk or ":" not in chunk:
            continue
        mime, _, extensions = chunk.partition(":")
        mime = mime.strip().lower()
        if not mime:
            continue
        names = ConcurrentStableFrozenList(
            dict.fromkeys(part.strip().lower() for part in extensions.split("|") if part.strip())
        )
        if not names:
            continue
        entry = WhitelistEntry(mime=mime, extensions=names)
        for name in names:
            mapping.set(name, entry)
    return mapping


def normalize_extension(name: str) -> str | None:
    """取文件名的规范扩展名（小写、无点；无扩展名 / 形态非法返回 None）。

    Args:
        name: 原始文件名。

    Returns:
        str | None: 扩展名；非法为 None。
    """
    _, dot, suffix = name.rpartition(".")
    if not dot:
        return None
    candidate = suffix.strip().lower()
    return candidate if _EXT_PATTERN.fullmatch(candidate) else None


def extension_of(name: str) -> str | None:
    """同 `normalize_extension`（语义别名，供调用点可读）。

    Args:
        name: 原始文件名。

    Returns:
        str | None: 扩展名；非法为 None。
    """
    return normalize_extension(name)


def sniff_mime(head: bytes) -> str | None:
    """按头部字节嗅探 MIME（未知返回 None）。

    Args:
        head: 头部字节（建议前 `SNIFF_LENGTH`）。

    Returns:
        str | None: 嗅探到的 MIME；无法判定为 None。
    """
    if head.startswith(_PDF_MAGIC):
        return "application/pdf"
    if head.startswith(_PNG_MAGIC):
        return "image/png"
    if head.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if head.startswith(_GIF_MAGICS):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(_ZIP_MAGIC):
        return ZIP_MIME
    return TEXT_MIME if _looks_like_text(head) else None


def resolve_mime(*, name: str, head: bytes, whitelist: ConcurrentStableDict[str, WhitelistEntry]) -> str:
    """校验扩展名与内容并给出落库 MIME。

    Args:
        name: 原始文件名。
        head: 头部字节（不足 512 字节时按实际长度）。
        whitelist: 解析后的白名单。

    Returns:
        str: 白名单里该扩展名对应的规范 MIME。

    Raises:
        ValueError: 扩展名缺失 / 不在白名单 / 内容与扩展名不相容。
    """
    extension = normalize_extension(name)
    if extension is None:
        raise ValueError("文件缺少可用扩展名")
    entry = whitelist.get(extension)
    if entry is None:
        raise ValueError(f"扩展名不在白名单：{extension}")
    sniffed = sniff_mime(head[:SNIFF_LENGTH])
    if sniffed is None:
        raise ValueError("无法识别文件内容类型")
    if extension in _OOXML_EXTENSIONS:
        if sniffed != ZIP_MIME:
            raise ValueError(f"内容与扩展名不相容：{extension} 应为 ZIP 容器，实际 {sniffed}")
        return entry.mime
    if not _compatible(entry.mime, sniffed):
        raise ValueError(f"内容与扩展名不相容：{extension} 应为 {entry.mime}，实际 {sniffed}")
    return entry.mime


def is_previewable(mime: str) -> bool:
    """是否支持在线预览（图片或 PDF）。

    Args:
        mime: 内容类型。

    Returns:
        bool: 可预览为 True。
    """
    return mime.startswith(_PREVIEW_PREFIX) or mime == _PREVIEW_EXTRA


def object_key_for(*, tenant: str | None, file_id: int, now: datetime | None = None) -> str:
    """派生对象 key（`{tenant_code}/files/{yyyy}/{mm}/{file_id}`）。

    Args:
        tenant: 租户编码（None 用 `global`）。
        file_id: 文件主键（雪花）。
        now: 时间（缺省当前 UTC）。

    Returns:
        str: 对象 key。
    """
    stamp = now if now is not None else datetime.now(UTC)
    scope = tenant or "global"
    return f"{scope}/files/{stamp:%Y}/{stamp:%m}/{file_id}"


def _compatible(mime: str, sniffed: str) -> bool:
    """规范 MIME 与嗅探结果是否相容（文本类互相兼容）。

    Args:
        mime: 白名单规范 MIME。
        sniffed: 嗅探结果。

    Returns:
        bool: 相容为 True。
    """
    if mime == sniffed:
        return True
    return mime.startswith("text/") and sniffed == TEXT_MIME


def _looks_like_text(head: bytes) -> bool:
    """启发式判定文本内容（无 NUL 且可解码 UTF-8，或全为 ASCII 字节）。

    Args:
        head: 头部字节。

    Returns:
        bool: 像文本为 True。
    """
    if not head or b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return all(byte < 0x80 for byte in head)
    return True
