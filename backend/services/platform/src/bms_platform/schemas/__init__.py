"""平台服务 schemas 层：Pydantic 请求 / 响应模型。

职责：请求校验与响应契约。
禁止：写业务逻辑；禁止直接返回 ORM 对象。
继承约定：请求 / 响应模型必须继承 `bms_core.schemas.BaseSchema`。
"""
