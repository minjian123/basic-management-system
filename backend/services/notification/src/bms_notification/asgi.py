"""ASGI 入口：模块级应用实例（`uvicorn bms_notification.asgi:app`）。"""

from bms_notification.main import ApplicationFactory

app = ApplicationFactory().create(None)
