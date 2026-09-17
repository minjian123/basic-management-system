/**
 * 权限判定契约用例工厂（框架无关）：各渲染插件传本实现的判定入口，跑同一套断言。
 *
 * 断言面：未注入语义（空码放行 / 非空拒绝）、注入后归一与透传（`string` → 单元素数组、
 * `mode` 传递、返回值透传）、恢复（`configure(undefined)`）回未注入语义。全确定性、无 UI 依赖。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PermissionChecker, PermissionMode } from '../src/contracts/permission'

export interface PermissionContractSubject {
  /** 插件出口：注入判定器（传 `undefined` 恢复未注入） */
  configure(next: PermissionChecker | undefined): void
  /** 插件出口：判定权限码 */
  check(code: string | string[] | null | undefined, mode?: PermissionMode): boolean
}

export function describePermissionContract(subject: PermissionContractSubject): void {
  describe('权限判定契约（permission）', () => {
    afterEach(() => {
      subject.configure(undefined)
    })

    it('未注入：空码放行、非空拒绝', () => {
      expect(subject.check(null)).toBe(true)
      expect(subject.check(undefined)).toBe(true)
      expect(subject.check('')).toBe(true)
      expect(subject.check([])).toBe(true)
      expect(subject.check('user:create')).toBe(false)
      expect(subject.check(['user:create', 'user:update'])).toBe(false)
    })

    it('注入后：string 归一为单元素数组、mode 传递、结果透传', () => {
      const checker = vi.fn((codes: readonly string[], mode: PermissionMode) => {
        expect(Array.isArray(codes)).toBe(true)
        return mode === 'all' ? codes.length > 1 : codes.length === 1
      })
      subject.configure(checker)

      expect(subject.check('user:create')).toBe(true)
      expect(checker).toHaveBeenLastCalledWith(['user:create'], 'any')

      expect(subject.check('user:create')).toBe(true)
      expect(checker).toHaveBeenLastCalledWith(['user:create'], 'any')

      expect(subject.check(['a', 'b'], 'all')).toBe(true)
      expect(checker).toHaveBeenLastCalledWith(['a', 'b'], 'all')

      expect(subject.check([])).toBe(true)
      expect(checker).toHaveBeenCalledTimes(3)
    })

    it('恢复：configure(undefined) 回未注入语义', () => {
      subject.configure(() => true)
      expect(subject.check('user:create')).toBe(true)
      subject.configure(undefined)
      expect(subject.check('user:create')).toBe(false)
      expect(subject.check(null)).toBe(true)
    })
  })
}
