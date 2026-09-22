"""平台地基 / 配置服务 api 层：业务路由与参数校验，只做参数校验与路由分发。

职责：路由聚合（router.py）、平台配置类模块路由（modules / plugins / dict / icon / preference /
query_scheme / codecheck / demo）。
依赖：接口层基座（路由基类 / 异常处理 / 中间件 / 探针 / 依赖提供者）来自 `bms_core.api`。
禁止：直接操作模型、写业务逻辑；业务规则一律经 services 层。
"""
