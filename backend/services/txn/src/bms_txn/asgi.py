"""ASGI 入口：模块级应用实例（`hypercorn bms_txn.asgi:app`）。"""

from bms_txn.main import ApplicationFactory

app = ApplicationFactory().create(None)
