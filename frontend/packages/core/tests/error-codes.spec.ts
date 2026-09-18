/** 错误码段位用例 + 契约用例工厂入口冒烟（02-7）。 */

import { expect, it } from 'vitest'

import { ErrorCodes, FRONTEND_RESERVED_SEGMENT, isFrontendReservedCode } from '../src'
import { describeContract } from '../testing'

describeContract('错误码段位契约', () => {
  it('内建码取平台段位（参数 / 未登记 / 冲突 / 限流 / 权限）', () => {
    expect(ErrorCodes.CAPABILITY_VIOLATION).toBe(10001)
    expect(ErrorCodes.PROVIDER_NOT_REGISTERED).toBe(10002)
    expect(ErrorCodes.REGISTRY_CONFLICT).toBe(10003)
    expect(ErrorCodes.RATE_LIMITED).toBe(10005)
    expect(ErrorCodes.PERMISSION_DENIED).toBe(30001)
  })

  it('未实现码落前端保留子段 19xxx', () => {
    expect(ErrorCodes.NOT_IMPLEMENTED).toBe(19001)
    expect(FRONTEND_RESERVED_SEGMENT).toEqual([19000, 19999])
    expect(isFrontendReservedCode(ErrorCodes.NOT_IMPLEMENTED)).toBe(true)
    expect(isFrontendReservedCode(ErrorCodes.REGISTRY_CONFLICT)).toBe(false)
  })
})
