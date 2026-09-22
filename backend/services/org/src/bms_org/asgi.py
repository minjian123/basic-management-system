"""ASGI 入口：模块级应用实例（`uvicorn bms_org.asgi:app`）。"""

from bms_org.main import ApplicationFactory

app = ApplicationFactory().create(None)
