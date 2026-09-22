"""ASGI 入口：模块级应用实例（`uvicorn bms_search.asgi:app`）。"""

from bms_search.main import ApplicationFactory

app = ApplicationFactory().create(None)
