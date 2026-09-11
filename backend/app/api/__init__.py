"""api 层：路由与参数校验，只做参数校验与路由分发。

职责：依赖注入（deps.py）、路由聚合（router.py）、模块路由（health/demo）。
禁止：直接操作模型、写业务逻辑；业务规则一律经 services 层。
"""
