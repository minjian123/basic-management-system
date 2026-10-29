"""认证服务装配面：把认证域实现装配给跨域消费方（域间依赖只在此处注入）。

用途单一：跨域消费方（如身份联邦域的 SSO 回调）需要**构造**认证域的实现对象，但出口只暴露
协议与 DTO——构造入口放这里，域实现之间仍然零 import（D1），装配方向恒为「装配面 → 域」。
本模块只做再导出与无参构造，不承载业务规则。
"""

from bms_identity.domains.auth.ports import SessionCookiePolicy as SessionCookiePolicy
from bms_identity.domains.auth.services.cookie_policy import HttpSessionCookiePolicy
from bms_identity.domains.auth.services.session_issuer import build_session_issuer as build_session_issuer

__all__ = ["build_cookie_policy", "build_session_issuer"]


def build_cookie_policy() -> SessionCookiePolicy:
    """构造 refresh cookie 策略（无状态；cookie 安全开关按请求的应用配置取）。

    Returns:
        SessionCookiePolicy: cookie 策略实现。
    """
    return HttpSessionCookiePolicy()
