"""认证与会话业务域公共出口（D2 唯一跨域引用面）。

只交两类：**不可变 DTO**（`IssuedSession`）与**领域服务接口**（`SessionIssuerPort` /
`SessionCookiePolicy`）。实现类（`SessionIssuer` / `HttpSessionCookiePolicy`）与装配工厂
（`build_session_issuer`）不出本出口——实现由 `bms_identity.wiring` 构造后注入，跨域消费方
只持协议与 DTO；改实现不影响出口面（出口形态由 D6 机器护栏守）。
"""

from bms_identity.domains.auth.dto import IssuedSession as IssuedSession
from bms_identity.domains.auth.ports import SessionCookiePolicy as SessionCookiePolicy
from bms_identity.domains.auth.ports import SessionIssuerPort as SessionIssuerPort

__all__ = ["IssuedSession", "SessionCookiePolicy", "SessionIssuerPort"]
