"""services 层：业务逻辑与事务边界（{模块}_service.py）。

职责：业务规则、事务边界（with session.begin()）、事件发布。
禁止：直接拼 SQL、绕过 repositories 访问数据。
"""
