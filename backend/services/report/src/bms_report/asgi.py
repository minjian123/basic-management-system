"""ASGI 入口：模块级应用实例（`hypercorn bms_report.asgi:app`）。"""

from bms_report.main import ApplicationFactory

app = ApplicationFactory().create(None)
