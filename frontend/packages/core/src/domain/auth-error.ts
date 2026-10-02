/**
 * 认证错误码文案（`2xxxx` 认证段 + `10005` 限流）。
 *
 * 与后端 `bms_core` 错误码登记同源，是 PC / 移动端共用的**文案单一来源**：宿主未引入国际化库时
 * 取本常量表；接入语言能力后本表转为缺省语言包，对外签名不变。
 * 验证码子段（`20101`~`20103`）复用 `CAPTCHA_ERROR_TEXTS`，不重复维护。
 */

import { CAPTCHA_ERROR_TEXTS } from './captcha'

/** 未登记错误码的通用回落文案。 */
export const DEFAULT_AUTH_ERROR_TEXT = '操作失败，请稍后重试'

/** 认证错误码文案表（`2xxxx` 认证段 + `10005` 限流；键为后端错误码）。 */
export const AUTH_ERROR_TEXTS: Readonly<Record<number, string>> = {
  10005: '请求过于频繁，请稍后重试',
  20001: '登录状态已失效，请重新登录',
  20002: '账号或密码错误',
  20003: '账号已锁定，请联系管理员或稍后重试',
  20004: '账号已停用，请联系管理员',
  20005: '重置链接无效或已过期',
  20006: '操作过于频繁，请稍后再试',
  20012: '登录状态已失效，请重新登录',
  20051: '登录方式不存在或已停用',
  20052: '登录校验失败，请重试',
  20053: '外部登录服务不可用，请改用账号密码登录',
  20054: '外部身份未匹配到系统用户',
  20055: '身份映射冲突，请联系管理员',
  20056: '登录过于频繁，请稍后再试',
  20057: '企业微信配置缺失或非法',
  20058: '企业微信授权失败',
  20059: '企业微信接口不可达',
  20060: '钉钉配置缺失或非法',
  20061: '钉钉授权失败',
  20062: '钉钉接口不可达',
}

/**
 * 是否认证错误码（命中本表或验证码子段）。
 *
 * @param code 错误码（任意类型；非数字返回 `false`）。
 * @returns 是否属认证段文案覆盖范围。
 */
export function isAuthErrorCode(code: unknown): boolean {
  return typeof code === 'number' && (code in AUTH_ERROR_TEXTS || code in CAPTCHA_ERROR_TEXTS)
}

/**
 * 错误码文案（本表 → 验证码子段 → 通用回落）。
 *
 * @param code 错误码（任意类型；非数字回落通用文案）。
 * @returns 中文文案。
 */
export function resolveAuthErrorText(code: unknown): string {
  if (typeof code !== 'number') {
    return DEFAULT_AUTH_ERROR_TEXT
  }
  if (code in AUTH_ERROR_TEXTS) {
    return AUTH_ERROR_TEXTS[code] as string
  }
  if (code in CAPTCHA_ERROR_TEXTS) {
    return CAPTCHA_ERROR_TEXTS[code] as string
  }
  return DEFAULT_AUTH_ERROR_TEXT
}
