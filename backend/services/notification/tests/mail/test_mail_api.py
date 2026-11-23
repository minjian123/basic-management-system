"""邮件 / 短信接口：模板 CRUD / 预览 / 发送 / 记录 / 权限。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.gate import GATE_CRITICAL_WAIT
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session

pytestmark = [pytest.mark.kiwi_id(2519), pytest.mark.asyncio(loop_scope="module")]

MAIL = "/api/v1/mail"
SMS = "/api/v1/sms"


@pytest.fixture
def codes(ns: Namespace) -> tuple[str, str]:
    """本用例的邮件 / 短信模板 code（按 nodeid 派生，避免与并行用例撞码）。"""
    return f"{ns.prefix}_welcome", f"{ns.prefix}_order"


@pytest.fixture(autouse=True)
async def _clean_templates_and_logs(shared_tenant_engine: AsyncEngine, codes: tuple[str, str]) -> AsyncIterator[None]:
    """用例前后只清本用例的模板与日志（写入立即落库，不再回滚）。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        codes: 本用例的模板 code。

    Yields:
        None: 用例运行期。
    """
    mail_code, sms_code = codes

    async def _purge() -> None:
        """删除本用例的模板（含多语言附表）与日志（原生 SQL 带 WHERE）。"""
        async with write_session(shared_tenant_engine, wait=GATE_CRITICAL_WAIT) as session:
            await session.execute(
                text(
                    "DELETE FROM sys_mail_template_i18n "
                    "WHERE template_id IN (SELECT id FROM sys_mail_template WHERE code = :code)"
                ),
                {"code": mail_code},
            )
            await session.execute(text("DELETE FROM sys_mail_template WHERE code = :code"), {"code": mail_code})
            await session.execute(text("DELETE FROM sys_mail_log WHERE template_code = :code"), {"code": mail_code})
            await session.execute(text("DELETE FROM sys_sms_template WHERE code = :code"), {"code": sms_code})
            await session.execute(text("DELETE FROM sys_sms_log WHERE template_code = :code"), {"code": sms_code})

    await _purge()
    yield
    await _purge()


def _mail_template(
    code: str, **overrides: object
) -> dict[str, object]:  # bare-collections:allow — httpx json 参数只接受内置 dict
    body: dict[str, object] = {
        "code": code,
        "name": "欢迎",
        "i18n": {
            "zh-CN": {"subject": "欢迎 {{ name }}", "content": "<p>你好 {{ name }}</p>"},
            "en-US": {"subject": "Welcome {{ name }}", "content": "<p>Hello {{ name }}</p>"},
        },
    }
    body.update(overrides)
    return body


def _sms_template(code: str) -> dict[str, object]:  # bare-collections:allow — httpx json 参数只接受内置 dict
    return {
        "code": code,
        "name": "订单通知",
        "content": "订单 {{ order_no }} 已发货。",
        "channel": "aliyun",
        "scene": "notify",
        "provider_template_id": "SMS_9",
        "provider_param_keys": ["order_no"],
    }


async def test_mail_api(
    service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine, codes: tuple[str, str]
) -> None:
    """邮件模板 CRUD / 预览 / 发送 / 记录。"""
    from mail._support import install

    mail_code, _sms_code = codes
    async with write_session(shared_tenant_engine) as session:
        jobs = install(service_app, session)
        created = await client.post(f"{MAIL}/templates", json=_mail_template(mail_code))
        assert created.status_code == 200, created.text
        template_id = created.json()["data"]["id"]

        listed = await client.get(f"{MAIL}/templates", params={"locale": "en-US"})
        assert listed.status_code == 200
        assert any(item["code"] == mail_code for item in listed.json()["data"]["list"])

        detail = await client.get(f"{MAIL}/templates/{template_id}", params={"locale": "zh-CN"})
        assert detail.json()["data"]["subject"] == "欢迎 {{ name }}"

        preview = await client.post(
            f"{MAIL}/templates/preview",
            json={"code": "approval_todo", "params": {"title": "审批", "content": "内容"}},
        )
        assert preview.status_code == 200
        assert "审批" in preview.json()["data"]["subject"]

        tested = await client.post(
            f"{MAIL}/templates/{template_id}/test", json={"params": {"name": "A"}, "locale": "en-US"}
        )
        assert tested.json()["data"]["subject"] == "Welcome A"

        sent = await client.post(
            f"{MAIL}/send",
            headers={"Idempotency-Key": f"{mail_code}-mail-1"},
            json={"template_code": mail_code, "params": {"name": "A"}, "recipient": "a@b.c"},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["data"]["status"] == "pending"
        assert jobs.calls[-1][0] == "notification.mail.send"

        logs = await client.get(f"{MAIL}/logs", params={"template_code": mail_code})
        assert logs.json()["data"]["total"] == 1

        updated = await client.put(f"{MAIL}/templates/{template_id}", json={"name": "欢迎2"})
        assert updated.json()["data"]["name"] == "欢迎2"
        deleted = await client.delete(f"{MAIL}/templates/{template_id}")
        assert deleted.json()["data"]["deleted"] is True


async def test_mail_syntax(
    service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine, codes: tuple[str, str]
) -> None:
    """语法错误保存即拒（70302）。"""
    from mail._support import install

    mail_code, _sms_code = codes
    async with write_session(shared_tenant_engine) as session:
        install(service_app, session)
        bad = await client.post(
            f"{MAIL}/templates",
            json=_mail_template(f"{mail_code}_bad", i18n={"zh-CN": {"subject": "x", "content": "{% if x %}"}}),
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == 70302


async def test_sms_api(
    service_app: FastAPI, client: AsyncClient, shared_tenant_engine: AsyncEngine, codes: tuple[str, str]
) -> None:
    """短信模板 CRUD / 列表 / 发送。"""
    from mail._support import install

    _mail_code, sms_code = codes
    async with write_session(shared_tenant_engine) as session:
        jobs = install(service_app, session)
        created = await client.post(f"{SMS}/templates", json=_sms_template(sms_code))
        assert created.status_code == 200, created.text
        template_id = created.json()["data"]["id"]

        listed = await client.get(f"{SMS}/templates", params={"source": "tenant"})
        assert any(item["code"] == sms_code for item in listed.json()["data"]["list"])
        detail = await client.get(f"{SMS}/templates/{template_id}")
        assert detail.json()["data"]["provider_template_id"] == "SMS_9"

        sent = await client.post(
            f"{SMS}/send",
            json={"template_code": sms_code, "params": {"order_no": "A1"}, "recipient": "13800000000"},
        )
        assert sent.status_code == 200, sent.text
        assert jobs.calls[-1][0] == "notification.sms.send"

        logs = await client.get(f"{SMS}/logs", params={"template_code": sms_code})
        assert logs.json()["data"]["total"] == 1
        assert "A1" in logs.json()["data"]["list"][0]["content"]
