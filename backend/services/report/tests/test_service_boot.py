"""BMS 报表打印服务服务启动冒烟（脚手架生成，02_03 拆分落位）。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_report import SERVICE_NAME, SERVICE_TITLE


@pytest.mark.kiwi_id(1206)
async def test_service_boots_and_exposes_probes(service_app: FastAPI, client: AsyncClient) -> None:
    """应用可构造且标题就位；`/healthz` 存活并携带服务身份；`/readyz` 响应携带身份（依赖状态可 200 / 503）。"""
    assert service_app.title == SERVICE_TITLE
    healthz = await client.get("/healthz")
    readyz = await client.get("/readyz")
    assert healthz.status_code == 200
    assert healthz.json()["service"] == SERVICE_NAME
    assert readyz.status_code in (200, 503)
    assert readyz.json()["service"] == SERVICE_NAME
