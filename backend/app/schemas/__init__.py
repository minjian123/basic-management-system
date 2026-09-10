"""schemas 层：Pydantic 请求/响应模型（base 基类、common 统一响应、{模块}.py）。

职责：请求校验与响应契约。
禁止：写业务逻辑；禁止直接返回 ORM 对象。
继承约定：请求/响应模型必须继承 BaseSchema（base.py）。
"""
