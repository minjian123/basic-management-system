/**
 * 帮助上下文契约用例工厂（`BaseHelpContext` 及其投影共用；`09_02` 首次落地）。
 *
 * 目标约定：取数器由用例注入；就绪后命中 / 有锚点无文章 / 失败三态由桩控制。
 */

import { describe, expect, it } from 'vitest'

/** 帮助上下文契约面。 */
export interface HelpContextContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 已发起请求计数（未就绪必须为 0）。 */
  readonly requestCount: number
  /** 是否命中文章。 */
  readonly matched: boolean
  /** 是否登记锚点。 */
  readonly anchorFound: boolean
  /** 错误文案。 */
  readonly errorMessage: string
  /** 分类名列表。 */
  readonly categoryNames: readonly string[]
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入取数器。 */
  setFetcher(fetcher: (query: Record<string, string>) => Promise<unknown>): void
  /** 设置上下文。 */
  setContext(context: Record<string, string>): void
  /** 解析（强制刷新可选）。 */
  resolve(force?: boolean): Promise<unknown>
  /** 重试。 */
  retry(): Promise<unknown>
}

/**
 * 帮助上下文契约（`BaseHelpContext` / `useBaseHelpContext` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeHelpContextContract(name: string, create: () => HelpContextContractTarget): void {
  describe(name, () => {
    it('未就绪零请求；就绪后命中文章并落 matched / anchorFound', async () => {
      const target = create()
      target.setContext({ module_key: 'm1' })
      await expect(target.resolve()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)

      target.setFetcher(async () => ({
        matched: true,
        anchor_found: true,
        level: 'module',
        article: { id: '1', title: '模块帮助', content: '<p>正文</p>', source: 'builtin' },
        categories: [{ id: '9', name: '快速上手', path: '快速上手' }],
      }))
      target.setReady(true)
      await target.resolve()
      expect(target.requestCount).toBe(1)
      expect(target.matched).toBe(true)
      expect(target.anchorFound).toBe(true)
      expect(target.categoryNames).toContain('快速上手')
    })

    it('有锚点无文章：anchorFound 真、matched 假；失败给文案并可重试', async () => {
      const target = create()
      target.setReady(true)
      target.setFetcher(async () => ({ matched: false, anchor_found: true, categories: [] }))
      await target.resolve()
      expect(target.matched).toBe(false)
      expect(target.anchorFound).toBe(true)

      let fail = true
      target.setFetcher(async () => {
        if (fail) {
          throw new Error('帮助服务不可用')
        }
        return { matched: true, anchor_found: true, article: { id: '2', title: '帮助', content: 'x' } }
      })
      target.setContext({ module_key: 'm2' })
      await target.resolve()
      expect(target.errorMessage).toBe('帮助服务不可用')

      fail = false
      await target.retry()
      expect(target.errorMessage).toBe('')
      expect(target.matched).toBe(true)
    })

    it('同上下文并发合并为一次请求', async () => {
      const target = create()
      let calls = 0
      target.setReady(true)
      target.setFetcher(async () => {
        calls += 1
        return { matched: false, anchor_found: false }
      })
      target.setContext({ module_key: 'm3' })
      await Promise.all([target.resolve(), target.resolve()])
      expect(calls).toBe(1)
      expect(target.requestCount).toBe(1)
    })
  })
}
