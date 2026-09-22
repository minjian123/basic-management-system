"""ASGI 入口：模块级应用实例（`uvicorn bms_identity.asgi:app`）。"""

from bms_identity.main import ApplicationFactory

app = ApplicationFactory().create(None)
