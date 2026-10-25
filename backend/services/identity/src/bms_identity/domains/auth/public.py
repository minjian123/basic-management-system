"""认证与会话业务域公共出口（D2 唯一跨域引用面）。

对外提供：会话签发（`build_session_issuer` / `SessionIssuer` / `IssuedSession`）与刷新 cookie 写入
（身份联邦域在 SSO 回调成功后签发会话时使用）。**本模块只做再导出**，不承载业务规则。
"""

from bms_identity.domains.auth.api.cookies import set_refresh_cookie as set_refresh_cookie
from bms_identity.domains.auth.services.session_issuer import (
    IssuedSession as IssuedSession,
)
from bms_identity.domains.auth.services.session_issuer import (
    SessionIssuer as SessionIssuer,
)
from bms_identity.domains.auth.services.session_issuer import (
    build_session_issuer as build_session_issuer,
)

__all__ = ["IssuedSession", "SessionIssuer", "build_session_issuer", "set_refresh_cookie"]
