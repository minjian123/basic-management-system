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
