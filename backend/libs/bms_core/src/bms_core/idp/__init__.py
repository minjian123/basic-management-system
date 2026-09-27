"""身份源能力域（外部 IdP 适配契约 + OIDC / CAS / 企微 / 钉钉真实实现 + 管理面支撑）。

- 契约与数据：`base.py`（授权 / 换码 / userinfo / 票据校验 / **连通性探测 `probe`**）。
- 实现：`oidc.py` / `cas.py` / `wecom.py` / `dingtalk.py` / `null.py`。
- 管理面支撑：`schema.py`（行配置声明式校验 + 凭据脱敏）、`ssrf.py`（出站 URL SSRF 校验）、
  `registry.py`（行配置实例化）。"""
