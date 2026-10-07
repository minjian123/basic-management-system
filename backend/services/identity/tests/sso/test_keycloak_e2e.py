"""Keycloak 真机联调 E2E（Kiwi 2197，integration 标记；缺配置或不可达自动跳过）。

凭据读仓库根 `deploy/.env`（不入仓）；由 Keycloak Admin API 幂等创建测试用户，
浏览器表单登录后回打本服务回调，验证授权码换码 + ID Token 校验 + 会话签发闭环。
"""

import html
import re
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_identity.api import sso as sso_api
from bms_identity.services.provider_registry import ProviderRegistry

from .conftest import SsoHarness
from .helpers import IDP_KEY, TENANT_HEADERS

pytestmark = [pytest.mark.integration, pytest.mark.kiwi_id(2197)]

_ENV_FILE = Path(__file__).resolve().parents[5] / "deploy" / ".env"
_USERNAME = "bms-sso-e2e"
_PASSWORD = "Bms-sso-e2e-2026!"
_USER_ID = 1001
_REGISTERED_REDIRECT = "http://localhost:8000/api/v1/auth/sso/keycloak/callback"
_REGISTERED_REDIRECT_EDGE = "http://localhost:8088/api/identity/v1/auth/sso/keycloak/callback"
_FORM_ACTION = re.compile(r'<form[^>]*\saction="([^"]+)"', re.IGNORECASE)
_INPUT_TAG = re.compile(r"<input\b[^>]*>", re.IGNORECASE)


def _load_env() -> ConcurrentStableDict[str, str]:
    """读取 deploy/.env 键值（注释与空行跳过）。

    Returns:
        ConcurrentStableDict[str, str]: 环境变量映射。
    """
    data: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            data.set(key.strip(), value.strip())
    return data


_ENV = _load_env()
_BASE = _ENV.get("KEYCLOAK_PUBLIC_URL", "").rstrip("/")
_ADMIN_USER = _ENV.get("KEYCLOAK_ADMIN_USERNAME", "")
_ADMIN_PASSWORD = _ENV.get("KEYCLOAK_ADMIN_PASSWORD", "")
_CLIENT_SECRET = _ENV.get("KEYCLOAK_CLIENT_SECRET", "")
_MISSING = (
    ""
    if all((_BASE, _ADMIN_USER, _ADMIN_PASSWORD, _CLIENT_SECRET))
    else "deploy/.env 缺 Keycloak 联调配置（KEYCLOAK_PUBLIC_URL / ADMIN_* / CLIENT_SECRET）"
)


def _attr(tag: str, name: str) -> str | None:
    """取 HTML 标签属性值（反转义）。

    Args:
        tag: 标签原文。
        name: 属性名。

    Returns:
        str | None: 属性值。
    """
    matched = re.search(rf'{name}="([^"]*)"', tag, re.IGNORECASE)
    return html.unescape(matched.group(1)) if matched else None


def _form_action(page: str) -> str:
    """提取登录页表单提交地址。

    Args:
        page: 页面 HTML。

    Returns:
        str: 表单 action URL。
    """
    matched = _FORM_ACTION.search(page)
    assert matched is not None, "Keycloak 登录页缺少表单 action"
    return html.unescape(matched.group(1))


def _form_fields(page: str) -> ConcurrentStableDict[str, str]:
    """提取登录页隐藏域（含 credentialId 等）。

    Args:
        page: 页面 HTML。

    Returns:
        ConcurrentStableDict[str, str]: 表单字段。
    """
    fields: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for tag in _INPUT_TAG.findall(page):
        name = _attr(tag, "name")
        value = _attr(tag, "value")
        if name and value is not None:
            fields.set(name, value)
    return fields


async def _ensure_redirect_uris(realm: httpx.AsyncClient, token: str) -> None:
    """确保 bms-backend 客户端登记本服务回调地址（存量实例自愈）。

    Args:
        realm: 真实网络客户端。
        token: 管理访问令牌。
    """
    headers = {"Authorization": f"Bearer {token}"}
    clients_url = f"{_BASE}/admin/realms/bms/clients"
    found = await realm.get(clients_url, headers=headers, params={"clientId": "bms-backend"})
    if found.status_code != 200 or not found.json():
        pytest.skip("Keycloak 缺 bms-backend 客户端（实仓未导入 bms-realm.json）")
    client: ConcurrentStableDict[str, object] = ConcurrentStableDict(found.json()[0])
    uris: ConcurrentStableList[str] = ConcurrentStableList(
        str(uri) for uri in cast("list[object]", client.get("redirectUris") or [])
    )
    missing = [uri for uri in (_REGISTERED_REDIRECT, _REGISTERED_REDIRECT_EDGE) if uri not in uris]
    if missing:
        updated = ConcurrentStableDict(client)
        updated.set("redirectUris", ConcurrentStableList([*uris, *missing]))
        put = await realm.put(f"{clients_url}/{client['id']}", headers=headers, json=dict(updated))
        if put.status_code not in (200, 204):
            pytest.skip(f"Keycloak 回调地址补登记失败（HTTP {put.status_code}）")


async def _admin_token(realm: httpx.AsyncClient) -> str:
    """获取 master realm 管理令牌（不可达即跳过）。

    Args:
        realm: 真实网络客户端。

    Returns:
        str: 管理访问令牌。
    """
    try:
        response = await realm.post(
            f"{_BASE}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": _ADMIN_USER,
                "password": _ADMIN_PASSWORD,
            },
        )
    except httpx.TransportError as exc:
        pytest.skip(f"Keycloak 不可达：{exc}")
    if response.status_code != 200:
        pytest.skip(f"Keycloak 管理令牌获取失败（HTTP {response.status_code}）")
    token = response.json().get("access_token")
    assert isinstance(token, str) and token
    return token


async def _ensure_user(realm: httpx.AsyncClient, token: str) -> str:
    """幂等创建测试用户并返回其 sub（realm 缺失即跳过）。

    Args:
        realm: 真实网络客户端。
        token: 管理访问令牌。

    Returns:
        str: 用户 id（即 ID Token 的 sub）。
    """
    headers = {"Authorization": f"Bearer {token}"}
    users_url = f"{_BASE}/admin/realms/bms/users"
    found = await realm.get(users_url, headers=headers, params={"username": _USERNAME, "exact": "true"})
    if found.status_code == 404:
        pytest.skip("Keycloak 未导入 bms realm（deploy/keycloak/bms-realm.json）")
    if found.status_code != 200:
        pytest.skip(f"Keycloak 用户查询失败（HTTP {found.status_code}）")
    rows = found.json()
    if not rows:
        created = await realm.post(
            users_url,
            headers=headers,
            json={
                "username": _USERNAME,
                "firstName": "SSO",
                "lastName": "E2E",
                "email": f"{_USERNAME}@example.com",
                "enabled": True,
                "emailVerified": True,
                "requiredActions": [],
                "credentials": [{"type": "password", "value": _PASSWORD, "temporary": False}],
            },
        )
        if created.status_code not in (201, 204):
            pytest.skip(f"Keycloak 测试用户创建失败（HTTP {created.status_code}）")
        found = await realm.get(users_url, headers=headers, params={"username": _USERNAME, "exact": "true"})
        rows = found.json()
    assert len(rows) == 1
    user = rows[0]
    user_id = user.get("id")
    assert isinstance(user_id, str) and user_id
    if not user.get("firstName") or not user.get("lastName") or user.get("requiredActions"):
        updated = dict(user)
        updated.update(
            {
                "firstName": "SSO",
                "lastName": "E2E",
                "email": f"{_USERNAME}@example.com",
                "enabled": True,
                "emailVerified": True,
                "requiredActions": [],
            }
        )
        patched = await realm.put(f"{users_url}/{user_id}", headers=headers, json=updated)
        if patched.status_code not in (200, 204):
            pytest.skip(f"Keycloak 测试用户资料补全失败（HTTP {patched.status_code}）")
    return user_id


@pytest.mark.kiwi_id(2197)
async def test_keycloak_end_to_end_login(
    client: httpx.AsyncClient,
    sso: SsoHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真机 E2E：授权跳转 → 表单登录 → 回调闭环（换码 + 验签 + 会话签发）。"""
    if _MISSING:
        pytest.skip(_MISSING)
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", _CLIENT_SECRET)
    monkeypatch.setattr(sso_api, "ProviderRegistry", ProviderRegistry)

    sso.platform_client.set_user(_USER_ID, username=_USERNAME)
    await sso.seed_provider(
        config=sso.provider_config(
            issuer=f"{_BASE}/realms/bms",
            client_secret_ref="env:KEYCLOAK_CLIENT_SECRET",
            redirect_uri=_REGISTERED_REDIRECT,
        )
    )

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as realm:
        admin_token = await _admin_token(realm)
        await _ensure_redirect_uris(realm, admin_token)
        subject = await _ensure_user(realm, admin_token)
        await sso.seed_mapping(external_id=subject)

        state, location, _ = await sso.start_flow(client)
        assert location.startswith(f"{_BASE}/realms/bms/protocol/openid-connect/auth")
        page = await realm.get(location)
        assert page.status_code == 200, page.text
        fields = _form_fields(page.text)
        fields.update({"username": _USERNAME, "password": _PASSWORD}.items())
        posted = await realm.post(_form_action(page.text), data=fields)
        assert posted.status_code == 302, posted.text
        redirect = urlparse(posted.headers["location"])
        code = parse_qs(redirect.query).get("code", [""])[0]
        assert code, posted.headers["location"]

    response = await client.get(
        f"/api/v1/auth/sso/{IDP_KEY}/callback?state={state}&code={code}",
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"tenant": "demo"}
    assert response.cookies["bms_refresh_token"].startswith("ref-")
