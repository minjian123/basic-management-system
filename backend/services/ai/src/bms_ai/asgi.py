"""ASGI 入口：模块级应用实例（`hypercorn bms_ai.asgi:app`）。"""

from bms_ai.main import ApplicationFactory

app = ApplicationFactory().create(None)
