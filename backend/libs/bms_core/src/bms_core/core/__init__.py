"""core 层：配置、安全与异常等基础能力（横切关注点）。

职责：配置加载（config.py）、安全工具（security.py）、异常体系（exceptions.py）。
禁止：引用 api/services/repositories 的业务代码；不承载业务逻辑。
"""
