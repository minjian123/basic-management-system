/**
 * 登录页领域纯函数：策略渠道选形、凭证归一与租户标识归一。
 *
 * 框架无关、零请求、可单测；PC 与移动端登录页同口径复用。
 */

import type { CaptchaCredential, CaptchaKind, CaptchaTracePoint } from '@bms/core'

import type { LoginRequest } from '@/api/identity'

/** 登录请求体中的验证码字段（契约生成类型，不手写重复定义）。 */
export type LoginCaptchaInput = NonNullable<LoginRequest['captcha']>

/** 登录表单值（登录页提交归一入参）。 */
export interface LoginFormValues {
  /** 登录账号（已去首尾空白）。 */
  account: string
  /** 登录口令明文。 */
  password: string
  /** 租户编码（归一后；空为 `null`）。 */
  tenant?: string | null
  /** 验证码凭证（可见且完备时携带）。 */
  captcha?: LoginCaptchaInput
  /** 记住我（缺省 `false`）。 */
  rememberMe?: boolean
}

/**
 * 组装登录请求体（契约 `LoginRequest`）。
 *
 * `remember_me` **恒显式携带**（缺省 `false`）；`tenant` 缺省归一为 `null`（由后端上下文解析）；
 * `captcha` 仅在提供时携带。密码不落任何存储。
 *
 * @param values 登录表单值。
 * @returns 契约登录请求体。
 */
export function buildLoginRequest(values: LoginFormValues): LoginRequest {
  const body: LoginRequest = {
    account: values.account,
    password: values.password,
    tenant: values.tenant ?? null,
    remember_me: values.rememberMe === true,
  }
  if (values.captcha !== undefined) {
    body.captcha = values.captcha
  }
  return body
}

/** 登录场景可渲染的验证码形态（登录无手机号来源，短信渠道不渲染）。 */
const LOGIN_RENDERABLE_KINDS: readonly CaptchaKind[] = ['slider', 'image']

/**
 * 按场景策略渠道序列选取登录页验证码形态（取首个**可渲染**形态）。
 *
 * 登录场景无手机号来源，`sms` 渠道跳过；`image` 恒为兜底形态。
 *
 * @param channels 策略下发的可用渠道（按降级顺序）。
 * @returns 选中的形态；无可渲染渠道返回 `null`（不显示验证码块）。
 */
export function pickLoginCaptchaKind(channels: readonly CaptchaKind[] | undefined): CaptchaKind | null {
  if (channels === undefined) {
    return null
  }
  for (const channel of channels) {
    if (LOGIN_RENDERABLE_KINDS.includes(channel)) {
      return channel
    }
  }
  return null
}

/**
 * 归一租户标识（去首尾空白；空串视为未填写）。
 *
 * @param input 输入框原始值。
 * @returns 归一后的租户编码；未填写返回 `null`（不随请求携带）。
 */
export function normalizeLoginTenant(input: string | undefined): string | null {
  const trimmed = (input ?? '').trim()
  return trimmed === '' ? null : trimmed
}

/**
 * 把件层凭证归一为契约 `CaptchaInput`（图形 / 短信带 `code`，滑块带 `trace`）。
 *
 * @param credential 件层上抛的凭证。
 * @returns 契约字段体（不做真伪判断）。
 */
export function toLoginCaptcha(credential: CaptchaCredential): LoginCaptchaInput {
  const payload: LoginCaptchaInput = {
    captcha_id: credential.captchaId,
    kind: credential.kind,
    code: credential.code ?? '',
  }
  if (credential.kind === 'slider' && credential.trace !== undefined) {
    payload.trace = toTraceTuples(credential.trace)
  }
  return payload
}

/**
 * 轨迹点对象序列转契约二元组序列（`[x, y, 相对起点毫秒]`）。
 *
 * @param trace 轨迹点序列。
 * @returns 契约轨迹序列。
 */
function toTraceTuples(trace: readonly CaptchaTracePoint[]): [number, number, number][] {
  return trace.map((point) => [point.x, point.y, point.t] as [number, number, number])
}
