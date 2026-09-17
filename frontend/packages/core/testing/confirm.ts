/**
 * 确认服务契约用例工厂（框架无关）：各渲染插件传本实现的可配置入口，跑同一套断言。
 *
 * 断言面：覆盖生效（options 透传 / 布尔透传 / rejection 原样传播）、多次覆盖取最后一次、
 * 恢复（`configure(undefined)`）后可再次配置；**不触发真实默认 UI**——默认实现行为由各插件自测。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ConfirmHandler, ConfirmOptions } from '../src/contracts/confirm'

export interface ConfirmContractSubject {
  /** 插件出口：覆盖确认实现（传 `undefined` 恢复默认） */
  configure(next: ConfirmHandler | undefined): void
  /** 插件出口：弹确认框 */
  confirm(options: ConfirmOptions): Promise<boolean>
}

export function describeConfirmContract(subject: ConfirmContractSubject): void {
  describe('确认服务契约（confirm）', () => {
    afterEach(() => {
      subject.configure(undefined)
    })

    it('覆盖生效：options 原样透传、布尔结果透传', async () => {
      const seen: ConfirmOptions[] = []
      subject.configure(async (options) => {
        seen.push(options)
        return true
      })
      const options: ConfirmOptions = {
        title: '标题',
        message: '内容',
        confirmText: '确定',
        cancelText: '取消',
        danger: true,
      }
      await expect(subject.confirm(options)).resolves.toBe(true)
      expect(seen).toEqual([options])

      subject.configure(async () => false)
      await expect(subject.confirm({ message: '再确认' })).resolves.toBe(false)
    })

    it('覆盖 rejection 原样传播（不做静默吞错）', async () => {
      const failure = new Error('override-reject')
      subject.configure(async () => {
        throw failure
      })
      await expect(subject.confirm({ message: '内容' })).rejects.toBe(failure)
    })

    it('多次覆盖取最后一次；恢复后可再次配置', async () => {
      const first = vi.fn(async () => true)
      const second = vi.fn(async () => false)
      subject.configure(first)
      subject.configure(second)
      await expect(subject.confirm({ message: '内容' })).resolves.toBe(false)
      expect(first).not.toHaveBeenCalled()
      expect(second).toHaveBeenCalledTimes(1)

      subject.configure(undefined)
      const third = vi.fn(async () => true)
      subject.configure(third)
      await expect(subject.confirm({ message: '内容' })).resolves.toBe(true)
      expect(third).toHaveBeenCalledTimes(1)
      expect(second).toHaveBeenCalledTimes(1)
    })
  })
}
