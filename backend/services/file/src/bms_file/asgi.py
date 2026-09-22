"""ASGI 入口：模块级应用实例（`uvicorn bms_file.asgi:app`）。"""

from bms_file.main import ApplicationFactory

app = ApplicationFactory().create(None)
