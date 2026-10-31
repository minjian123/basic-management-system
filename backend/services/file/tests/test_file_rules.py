"""文件域规则测试（Kiwi 2374）：扩展名 / 嗅探 / 白名单 / 对象 key / 预览判定。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_file.domains.file.rules import (
    DEFAULT_WHITELIST,
    WhitelistEntry,
    is_previewable,
    normalize_extension,
    object_key_for,
    parse_whitelist,
    resolve_mime,
    sniff_mime,
)

pytestmark = pytest.mark.kiwi_id(2374)

_WHITELIST = parse_whitelist(DEFAULT_WHITELIST)


def test_parse_whitelist_skips_invalid_entries() -> None:
    """白名单解析：非法条目（缺冒号 / 空扩展名 / 空 MIME）跳过，多扩展名共用一条。"""
    parsed = parse_whitelist("image/png:png,,:jpg,bad-entry,text/plain:,image/jpeg:jpg|jpeg")
    assert set(parsed) == {"png", "jpg", "jpeg"}
    assert parsed["jpg"].mime == "image/jpeg"
    assert parsed["jpeg"] is parsed["jpg"]


def test_parse_whitelist_default_covers_documented_types() -> None:
    """缺省白名单覆盖图片 / PDF / OOXML / 文本 / CSV。"""
    assert set(_WHITELIST) == {"png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "xlsx", "pptx", "txt", "csv"}


def test_normalize_extension_rules() -> None:
    """扩展名：小写化、无点、无扩展名 / 非法形态返回 None。"""
    assert normalize_extension("a.PDF") == "pdf"
    assert normalize_extension("archive.tar.gz") == "gz"
    assert normalize_extension("noext") is None
    assert normalize_extension("a.") is None
    assert normalize_extension("a.toolongextensionname") is None
    assert normalize_extension("a.p df") is None


def test_sniff_mime_recognizes_documented_magics() -> None:
    """嗅探识别 PDF / PNG / JPEG / GIF / WEBP / ZIP / 文本；未知返回 None。"""
    assert sniff_mime(b"%PDF-1.7 rest") == "application/pdf"
    assert sniff_mime(bytes.fromhex("89504e470d0a1a0a") + b"rest") == "image/png"
    assert sniff_mime(bytes.fromhex("ffd8ffe0") + b"rest") == "image/jpeg"
    assert sniff_mime(b"GIF89a-rest") == "image/gif"
    assert sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_mime(b"PK\x03\x04rest") == "application/zip"
    assert sniff_mime(b"plain text body") == "text/plain"
    assert sniff_mime(bytes.fromhex("4d5a90")) is None
    assert sniff_mime(b"") is None


def test_resolve_mime_accepts_matching_type() -> None:
    """扩展名与内容相符时返回白名单规范 MIME（不采信客户端声明）。"""
    assert resolve_mime(name="a.pdf", head=b"%PDF-1.4", whitelist=_WHITELIST) == "application/pdf"
    assert resolve_mime(name="a.PNG", head=bytes.fromhex("89504e470d0a1a0a"), whitelist=_WHITELIST) == "image/png"
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert resolve_mime(name="a.docx", head=b"PK\x03\x04rest", whitelist=_WHITELIST) == docx
    assert resolve_mime(name="a.csv", head=b"a,b\n1,2\n", whitelist=_WHITELIST) == "text/csv"


def test_resolve_mime_rejects_renamed_and_mismatched() -> None:
    """改扩展名绕过 / 无扩展名 / 未知内容 / OOXML 非 ZIP 容器一律拒绝。"""
    with pytest.raises(ValueError, match="内容与扩展名不相容"):
        resolve_mime(name="evil.pdf", head=bytes.fromhex("89504e470d0a1a0a"), whitelist=_WHITELIST)
    with pytest.raises(ValueError, match="不在白名单"):
        resolve_mime(name="a.exe", head=b"MZ", whitelist=_WHITELIST)
    with pytest.raises(ValueError, match="缺少可用扩展名"):
        resolve_mime(name="noext", head=b"%PDF-1.4", whitelist=_WHITELIST)
    with pytest.raises(ValueError, match="无法识别文件内容类型"):
        resolve_mime(name="a.pdf", head=bytes.fromhex("4d5a90"), whitelist=_WHITELIST)
    with pytest.raises(ValueError, match="应为 ZIP 容器"):
        resolve_mime(name="a.docx", head=b"%PDF-1.4", whitelist=_WHITELIST)


def test_resolve_mime_handles_text_family() -> None:
    """文本族：`text/csv` 接受纯文本嗅探结果；二进制不符合文本扩展名。"""
    assert resolve_mime(name="a.txt", head=b"plain", whitelist=_WHITELIST) == "text/plain"
    with pytest.raises(ValueError, match="内容与扩展名不相容"):
        resolve_mime(name="a.txt", head=bytes.fromhex("ffd8ffe0"), whitelist=_WHITELIST)


def test_is_previewable_only_images_and_pdf() -> None:
    """预览白名单：图片与 PDF，其它类型拒绝。"""
    assert is_previewable("image/png") is True
    assert is_previewable("application/pdf") is True
    assert is_previewable("text/csv") is False


def test_object_key_shape() -> None:
    """对象 key：租户前缀 + `files/年/月/文件ID`；无租户用 `global`。"""
    from datetime import UTC, datetime

    moment = datetime(2026, 10, 31, tzinfo=UTC)
    assert object_key_for(tenant="acme", file_id=42, now=moment) == "acme/files/2026/10/42"
    assert object_key_for(tenant=None, file_id=42, now=moment) == "global/files/2026/10/42"


def test_whitelist_entry_is_value_object() -> None:
    """白名单条目为不可变值对象（同值相等）。"""
    first = WhitelistEntry(mime="image/png", extensions=ConcurrentStableFrozenList(("png",)))
    second = WhitelistEntry(mime="image/png", extensions=ConcurrentStableFrozenList(("png",)))
    assert first == second
    assert "image/png" in repr(first)
