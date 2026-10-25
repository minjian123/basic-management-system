"""业务域实现根：一域一目录（目录名 = `domain_key`），域内按层组织。"""

from bms_core.core.concurrent import ConcurrentStableList

DOMAINS: ConcurrentStableList[str] = ConcurrentStableList("tenant")
"""本服务承载的业务域（与域布局声明的 `service_key` 反向一致；护栏断言）。"""
