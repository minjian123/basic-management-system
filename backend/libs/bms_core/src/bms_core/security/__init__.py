"""security 能力域包：安全原语插件契约与实现（口令哈希 / 令牌编解码 / 会话安全）。

- 契约：`base.py`（`BaseSecurity` 中间层 + 三插件基类 + 三 `get_*` 提供者）。
- 真实实现：`pbkdf2.py`（口令哈希）、`jwt.py`（令牌编解码）、`session.py`（会话安全）。
- 缺省实现：`null.py`（fail-closed，未配置真实实现即拒绝）。
"""
