// kiwi_id: 2232, 2240
/** 认证错误码文案用例（05_01 / 05_06）：文案表命中 / 验证码子段复用 / 通用回落与判定。 */

import { describe, expect, it } from 'vitest'

import { AUTH_ERROR_TEXTS, DEFAULT_AUTH_ERROR_TEXT, isAuthErrorCode, resolveAuthErrorText } from '../src'

describe('认证错误码文案（Kiwi 2232）', () => {
  it('认证段错误码逐项命中文案（登录 / 会话 / SSO / 企微钉钉）', () => {
    expect(resolveAuthErrorText(20002)).toBe('账号或密码错误')
    expect(resolveAuthErrorText(20003)).toBe('账号已锁定，请联系管理员或稍后重试')
    expect(resolveAuthErrorText(20004)).toBe('账号已停用，请联系管理员')
    expect(resolveAuthErrorText(20001)).toBe('登录状态已失效，请重新登录')
    expect(resolveAuthErrorText(20007)).toBe('请填写租户标识（当前部署存在多个租户）')
    expect(resolveAuthErrorText(20012)).toBe('登录状态已失效，请重新登录')
    expect(resolveAuthErrorText(20053)).toBe('外部登录服务不可用，请改用账号密码登录')
    expect(resolveAuthErrorText(20057)).toBe('企业微信配置缺失或非法')
    expect(resolveAuthErrorText(20062)).toBe('钉钉接口不可达')
    expect(resolveAuthErrorText(10005)).toBe('请求过于频繁，请稍后重试')
    expect(resolveAuthErrorText(10007)).toBe('服务暂不可用，请稍后重试')
  })

  it('验证码子段（20101 ~ 20103）回落验证码文案表，不重复维护', () => {
    expect(resolveAuthErrorText(20101)).toBe('验证码错误')
    expect(resolveAuthErrorText(20102)).toBe('验证码已失效，请重新获取')
    expect(resolveAuthErrorText(20103)).toBe('发送过于频繁，请稍后再试')
  })

  it('未登记码与非数字入参回落通用文案', () => {
    expect(resolveAuthErrorText(99999)).toBe(DEFAULT_AUTH_ERROR_TEXT)
    expect(resolveAuthErrorText(0)).toBe(DEFAULT_AUTH_ERROR_TEXT)
    expect(resolveAuthErrorText(undefined)).toBe(DEFAULT_AUTH_ERROR_TEXT)
    expect(resolveAuthErrorText(null)).toBe(DEFAULT_AUTH_ERROR_TEXT)
  })

  it('数字字符串码同样命中（异常经字符串化链路到达时不再丢文案）', () => {
    expect(resolveAuthErrorText('20002')).toBe('账号或密码错误')
    expect(resolveAuthErrorText('20101')).toBe('验证码错误')
    expect(resolveAuthErrorText(' 10007 ')).toBe('服务暂不可用，请稍后重试')
    expect(isAuthErrorCode('20103')).toBe(true)
    expect(resolveAuthErrorText('abc')).toBe(DEFAULT_AUTH_ERROR_TEXT)
    expect(resolveAuthErrorText('')).toBe(DEFAULT_AUTH_ERROR_TEXT)
  })

  it('isAuthErrorCode 覆盖本表与验证码子段', () => {
    expect(isAuthErrorCode(20002)).toBe(true)
    expect(isAuthErrorCode(20101)).toBe(true)
    expect(isAuthErrorCode(10005)).toBe(true)
    expect(isAuthErrorCode(99999)).toBe(false)
    // 数字字符串同样命中（异常经字符串化链路到达时不丢文案）。
    expect(isAuthErrorCode('20002')).toBe(true)
    expect(isAuthErrorCode('20101')).toBe(true)
    expect(isAuthErrorCode('abc')).toBe(false)
    expect(isAuthErrorCode(undefined)).toBe(false)
  })

  it('文案表键位均为认证段 / 限流码（无越界条目）', () => {
    const keys = Object.keys(AUTH_ERROR_TEXTS).map(Number)
    expect(keys.every((code) => code === 10005 || code === 10007 || (code >= 20001 && code <= 29999))).toBe(true)
    expect(keys.every((code) => (AUTH_ERROR_TEXTS[code] as string).length > 0)).toBe(true)
  })
})
