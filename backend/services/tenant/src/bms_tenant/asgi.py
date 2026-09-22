"""ASGI 入口：模块级应用实例（`uvicorn bms_tenant.asgi:app`）。"""

from bms_tenant.main import ApplicationFactory

app = ApplicationFactory().create(None)
