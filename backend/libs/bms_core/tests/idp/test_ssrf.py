"""外部 IdP 出站 URL SSRF 校验测试（Kiwi 2203）。"""

import pytest

from bms_core.core.exceptions import IdpConfigInvalidError
from bms_core.idp.ssrf import validate_browser_url, validate_outbound_url


@pytest.mark.kiwi_id(2203)
def test_outbound_protocol_whitelist() -> None:
    """协议非 http(s) / 空 / 缺主机拒绝。"""
    with pytest.raises(IdpConfigInvalidError):
        validate_outbound_url("ftp://idp.example.com", allow_private_hosts=False)
    with pytest.raises(IdpConfigInvalidError):
        validate_outbound_url("", allow_private_hosts=False)
    with pytest.raises(IdpConfigInvalidError):
        validate_outbound_url("https://", allow_private_hosts=False)


@pytest.mark.kiwi_id(2203)
def test_outbound_blocks_private_and_metadata() -> None:
    """本机 / 私网 / 回环 / 链路本地 / 元数据地址拒绝。"""
    blocked = [
        "http://localhost",
        "http://sub.localhost/x",
        "http://127.0.0.1:8090",
        "http://10.0.0.5",
        "http://172.16.1.1",
        "http://192.168.1.10",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]:8090",
        "http://0.0.0.0",
    ]
    for url in blocked:
        with pytest.raises(IdpConfigInvalidError):
            validate_outbound_url(url, allow_private_hosts=False)


@pytest.mark.kiwi_id(2203)
def test_outbound_allows_public_domain_and_private_when_enabled() -> None:
    """公网域名通过；开启 `allow_private_hosts` 后内网 / 回环放行。"""
    assert validate_outbound_url("https://idp.example.com/realms/bms", allow_private_hosts=False) == (
        "https://idp.example.com/realms/bms"
    )
    assert validate_outbound_url("http://127.0.0.1:8090", allow_private_hosts=True) == "http://127.0.0.1:8090"
    assert validate_outbound_url("http://keycloak:8090", allow_private_hosts=True) == "http://keycloak:8090"
    assert validate_outbound_url("https://93.184.216.34/realms/bms", allow_private_hosts=False) == (
        "https://93.184.216.34/realms/bms"
    )


@pytest.mark.kiwi_id(2203)
def test_browser_url_protocol_only() -> None:
    """浏览器跳转地址仅校验协议 + 主机（不做内网校验）。"""
    assert validate_browser_url("http://127.0.0.1/cb") == "http://127.0.0.1/cb"
    with pytest.raises(IdpConfigInvalidError):
        validate_browser_url("ftp://app.example.com/cb")
    with pytest.raises(IdpConfigInvalidError):
        validate_browser_url("https://")
