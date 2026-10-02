/**
 * 认证端点封装：服务段寻址 + **生成类型消费**（不手写重复类型定义）。
 *
 * 响应类型全部取 `@bms/api-types` 的 `identity` 命名空间（需求 06-1 / 06-3 / 06-4 的零漂移门禁）；
 * refresh / logout 为**会话动作**（非业务写），用核心 `request` 显式发起、不自动附幂等键。
 */

import type { identity } from '@bms/api-types'
import { request } from '@bms/core'

import { apiUrl } from './request'

/** 登录请求体（identity 契约生成类型）。 */
export type LoginRequest = identity.components['schemas']['LoginRequest']

/** 登录结果（access + 用户概要；refresh 走 httpOnly cookie）。 */
export type LoginResult = identity.components['schemas']['LoginResult']

/** 刷新结果（新 access；新 refresh 走 httpOnly cookie）。 */
export type RefreshResult = identity.components['schemas']['RefreshResult']

/** 用户概要（登录与 `/auth/me` 同字段、同语义）。 */
export type UserSummary = identity.components['schemas']['UserSummary']

/**
 * 本地账号密码登录（凭据端点；登录页消费）。
 *
 * @param body 登录请求体。
 */
export function login(body: LoginRequest): Promise<LoginResult> {
  return request<LoginResult>({ method: 'POST', url: apiUrl('identity', '/auth/login'), data: body })
}

/** 静默刷新（携带 httpOnly refresh cookie；无会话返回 401）。 */
export function refreshAccessToken(): Promise<RefreshResult> {
  return request<RefreshResult>({ method: 'POST', url: apiUrl('identity', '/auth/refresh') })
}

/** 登出（幂等：refresh 入黑名单 + 会话撤销；清 refresh cookie）。 */
export function logout(): Promise<void> {
  return request<void>({ method: 'POST', url: apiUrl('identity', '/auth/logout') })
}

/** 当前用户概要（首屏静默续期恢复用户上下文）。 */
export function fetchCurrentUser(): Promise<UserSummary> {
  return request<UserSummary>({ method: 'GET', url: apiUrl('identity', '/auth/me') })
}

/** SSO 入口清单项（登录页按此渲染 IdP 入口）。 */
export type SsoProviderItem = identity.components['schemas']['SsoProviderItem']

/** SSO 入口清单响应体（仅启用项；无启用 IdP 时 `items` 为空）。 */
export type SsoProviderList = identity.components['schemas']['SsoProviderList']

/**
 * 取当前租户可用 SSO 入口清单（免登录端点）。
 *
 * @param tenant 租户编码（可选；缺省由后端按上下文 / 子域名解析）。
 * @returns SSO 入口清单。
 */
export function fetchSsoProviders(tenant?: string | null): Promise<SsoProviderList> {
  const params = tenant === undefined || tenant === null || tenant === '' ? undefined : { tenant }
  return request<SsoProviderList>({
    method: 'GET',
    url: apiUrl('identity', '/auth/sso/providers'),
    params,
  })
}

/**
 * 组装 SSO 授权跳转地址（**顶层地址跳转**、非 XHR：后端 `302` 到外部 IdP）。
 *
 * 只拼「站内服务段地址 + 查询参数」，不拼外部地址（防开放重定向）。
 *
 * @param idpKey IdP 标识（清单项 `idp_key`）。
 * @param tenant 租户编码（可选；缺省由后端解析）。
 * @returns 授权跳转地址。
 */
export function ssoAuthorizeUrl(idpKey: string, tenant?: string | null): string {
  const base = apiUrl('identity', `/auth/sso/${encodeURIComponent(idpKey)}/authorize`)
  if (tenant === undefined || tenant === null || tenant === '') {
    return base
  }
  return `${base}?tenant=${encodeURIComponent(tenant)}`
}
