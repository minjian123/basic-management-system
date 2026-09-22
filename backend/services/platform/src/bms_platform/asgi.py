"""ASGI 入口：模块级应用实例（`uvicorn bms_platform.asgi:app`）。

应用构造统一经 `ApplicationFactory`（02-54 工厂基座）；本模块只提供 ASGI 服务器所需的模块级实例。
"""

from bms_platform.main import ApplicationFactory

app = ApplicationFactory().create(None)
