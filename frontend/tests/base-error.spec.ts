/** 错误基类用例（Kiwi 703）：响应解析 / 提示映射 / 段位判定 / 上报委托（双端同款）。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resetFrontendBaseConfig } from '@/base/BaseFrontend'
import {
  BaseError,
  ERROR_MESSAGES,
  NOT_IMPLEMENTED_CODE,
  PERMISSION_CODE,
  RATE_LIMIT_CODE,
  messageForCode,
  registerErrorMessages,
} from '@/base/error'

beforeEach(() => {
  resetFrontendBaseConfig()
})

describe('错误基类（Kiwi 703）', () => {
  it('㉑ fromResponse：code ≠ 0 构造；code === 0 或结构不符返回 null', () => {
    const error = BaseError.fromResponse({ code: 30001, message: '权限不足', data: { id: 7 } })
    expect(error).toBeInstanceOf(BaseError)
    expect(error?.code).toBe(PERMISSION_CODE)
    expect(error?.message).toBe('权限不足')
    expect(error?.data).toEqual({ id: 7 })

    expect(BaseError.fromResponse({ code: 0, message: 'ok' })).toBeNull()
    expect(BaseError.fromResponse(null)).toBeNull()
    expect(BaseError.fromResponse('boom')).toBeNull()
    expect(BaseError.fromResponse({ message: 'missing-code' })).toBeNull()
    expect(BaseError.fromResponse({ message: 'missing-code' }, RATE_LIMIT_CODE)?.code).toBe(RATE_LIMIT_CODE)
    expect(BaseError.fromResponse({ code: 10005 })?.message).toBe('[10005]')
  })

  it('㉒ toUserMessage 三级：i18n 命中 → 静态映射 → 通用回退', () => {
    const i18nBase = {
      t: (key: string) => (key === `error.${PERMISSION_CODE}` ? '没有权限访问' : key),
    }
    expect(new BaseError({ code: PERMISSION_CODE }).toUserMessage(i18nBase)).toBe('没有权限访问')

    const emptyI18nBase = { t: (key: string) => key }
    expect(new BaseError({ code: PERMISSION_CODE }).toUserMessage(emptyI18nBase)).toBe(ERROR_MESSAGES[PERMISSION_CODE])
    expect(new BaseError({ code: 49999 }).toUserMessage(emptyI18nBase)).toBe('操作失败，请稍后重试')
    expect(new BaseError({ code: 49999, userMessage: '自定义提示' }).toUserMessage(emptyI18nBase)).toBe('自定义提示')
    expect(new BaseError({ code: 49999 }).toUserMessage()).toBe('操作失败，请稍后重试')
  })

  it('㉓ 段位判定：isAuth / isPermission / isRateLimit', () => {
    expect(new BaseError({ code: 20001 }).isAuth()).toBe(true)
    expect(new BaseError({ code: 10001 }).isAuth()).toBe(false)
    expect(new BaseError({ code: PERMISSION_CODE }).isPermission()).toBe(true)
    expect(new BaseError({ code: 30002 }).isPermission()).toBe(false)
    expect(new BaseError({ code: RATE_LIMIT_CODE }).isRateLimit()).toBe(true)
    expect(new BaseError({ code: NOT_IMPLEMENTED_CODE }).isRateLimit()).toBe(false)
  })

  it('㉔ report 委托根系 reportError 并携带错误码元信息', () => {
    const reportError = vi.fn()
    const error = new BaseError({ code: 30001, message: '权限不足' })
    error.report({ reportError }, { page: '/sys/user' })

    expect(reportError).toHaveBeenCalledTimes(1)
    expect(reportError.mock.calls[0]?.[0]).toBe(error)
    expect(reportError.mock.calls[0]?.[1]).toMatchObject({
      code: 30001,
      name: 'BaseError',
      page: '/sys/user',
    })
  })

  it('㉕ instanceof Error 成立，name / stack / cause 保留', () => {
    const cause = new Error('原始错误')
    const error = new BaseError({ code: 10005, message: 'too many', cause })
    expect(error instanceof Error).toBe(true)
    expect(error.name).toBe('BaseError')
    expect(typeof error.stack).toBe('string')
    expect(error.cause).toBe(cause)
    expect(String(error)).toContain('too many')
  })

  it('㉖ registerErrorMessages 追加映射生效；未映射返回 undefined', () => {
    expect(messageForCode(40001)).toBeUndefined()
    registerErrorMessages({ 40001: '配置错误' })
    expect(messageForCode(40001)).toBe('配置错误')
    expect(new BaseError({ code: 40001 }).toUserMessage({ t: (key) => key })).toBe('配置错误')
  })
})
