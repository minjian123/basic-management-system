"""HTTP/2 运行时真网络冒烟：HTTP/1.1、h2c prior knowledge、TLS ALPN（Kiwi 2419）。"""

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI

from bms_core.core.config import Settings
from bms_core.core.run import serve_service


def _free_port() -> int:
    """取一个本机空闲端口（关闭 socket 后由 hypercorn 重新绑定）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _app() -> FastAPI:
    """最小 ASGI 应用：只提供 `/ping`。"""
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:  # bare-collections:allow（FastAPI 端点返回注解）
        return {"ok": True}

    return app


def _settings(port: int) -> Settings:
    """按测试端口构造配置（不启用 TLS）。"""
    settings = Settings()
    settings.server.host = "127.0.0.1"
    settings.server.port = port
    return settings


async def _wait_ready(client: httpx.AsyncClient) -> None:
    """等待服务可请求（最多约 5s）。"""
    last: Exception | None = None
    for _ in range(100):
        try:
            response = await client.get("/ping")
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:  # 端口尚未监听
            last = exc
        await asyncio.sleep(0.05)
    raise AssertionError(f"服务未就绪：{last}")


async def _run_http_scenario(settings: Settings) -> None:
    """启动服务并验证 HTTP/1.1 与 h2c。"""
    task = asyncio.create_task(serve_service(_app(), settings))
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{settings.server.port}") as client:
            await _wait_ready(client)
            response = await client.get("/ping")
            assert response.status_code == 200
            assert response.http_version == "HTTP/1.1"

        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{settings.server.port}",
            http2=True,
            http1=False,
        ) as client:
            response = await client.get("/ping")
            assert response.status_code == 200
            assert response.http_version == "HTTP/2"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.kiwi_id(2419)
def test_http1_and_h2c_prior_knowledge() -> None:
    """明文：HTTP/1.1 正常；`httpx(http2=True)` 以 h2c prior knowledge 协商 HTTP/2。"""
    asyncio.run(_run_http_scenario(_settings(_free_port())))


def _write_self_signed_cert(tmp_path: Path) -> tuple[Path, Path]:
    """生成自签证书与私钥（仅测试用）。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@pytest.mark.kiwi_id(2419)
def test_tls_alpn_negotiates_h2(tmp_path: Path) -> None:
    """TLS：`httpx(http2=True, verify=False)` 通过 ALPN 协商到 HTTP/2。"""
    cert_path, key_path = _write_self_signed_cert(tmp_path)
    settings = _settings(_free_port())
    settings.server.certfile = str(cert_path)
    settings.server.keyfile = str(key_path)

    async def _scenario() -> None:
        task = asyncio.create_task(serve_service(_app(), settings))
        try:
            async with httpx.AsyncClient(
                base_url=f"https://127.0.0.1:{settings.server.port}",
                http2=True,
                verify=False,
            ) as client:
                await _wait_ready(client)
                response = await client.get("/ping")
                assert response.status_code == 200
                assert response.http_version == "HTTP/2"
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(_scenario())
