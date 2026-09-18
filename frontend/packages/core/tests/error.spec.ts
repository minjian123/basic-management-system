/** 错误基座 `BaseError` 用例（02-5）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { BaseError, ErrorCodes, configureBase, resetBaseSinks } from '../src'

afterEach(() => resetBaseSinks())

describe('BaseError 错误基座', () => {
  it('保留 Error 语义（instanceof / 堆栈 / name）', () => {
    const error = new BaseError(ErrorCodes.NOT_IMPLEMENTED, '未实现')
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('BaseError')
    expect(typeof error.stack).toBe('string')
  })

  it('错误码与用户提示', () => {
    const error = new BaseError(ErrorCodes.REGISTRY_CONFLICT, '重复登记', { userMessage: '已存在' })
    expect(error.code).toBe(10003)
    expect(error.userMessage).toBe('已存在')
    expect(error.message).toBe('重复登记')
  })

  it('因果链（cause）', () => {
    const cause = new Error('root')
    expect(new BaseError(10001, 'x', { cause }).cause).toBe(cause)
  })

  it('具备总基类公共面（日志 / 生命周期）', () => {
    const logger = vi.fn()
    configureBase({ logger })
    const error = new BaseError(19001, 'x')
    error.log('warn', 'hi')
    expect(logger).toHaveBeenCalledWith('warn', '[bms:error] hi', undefined)
    expect(error.isDisposed).toBe(false)
    error.dispose()
    expect(error.isDisposed).toBe(true)
  })
})
