// kiwi_id: 2525
/** 帮助上下文能力基类（09_02）：未就绪零请求 / 三态 / 同上下文合并 / 竞态丢弃 / 未注入报错。 */

import { describe, expect, it } from 'vitest'

import { BaseHelpContext } from '@bms/core'
import { describeHelpContextContract, type HelpContextContractTarget } from '@bms/core/testing'

/** 可实例化帮助上下文。 */
class HelpContextState extends BaseHelpContext {}

/**
 * 把能力适配为契约目标。
 *
 * @returns 契约目标。
 */
function makeTarget(): HelpContextContractTarget {
  const context = new HelpContextState()
  return {
    get ready() {
      return context.ready
    },
    get requestCount() {
      return context.requestCount
    },
    get matched() {
      return context.matched
    },
    get anchorFound() {
      return context.anchorFound
    },
    get errorMessage() {
      return context.errorMessage
    },
    get categoryNames() {
      return context.categories.map((item) => item.name)
    },
    setReady: (value) => context.setReady(value),
    setFetcher: (fetcher) => context.setFetcher(async (query) => fetcher(query)),
    setContext: (input) =>
      context.setContext({
        moduleKey: input.module_key,
        formKey: input.form_key,
        fieldKey: input.field_key,
        actionCode: input.action_code,
        productKey: input.product_key,
      }),
    resolve: (force = false) => context.resolve(force),
    retry: () => context.retry(),
  }
}

describe('帮助上下文基类（09_02）', () => {
  describeHelpContextContract('帮助上下文契约', makeTarget)

  it('同上下文缓存结果：不强制刷新不重复请求，强制刷新重取', async () => {
    const context = new HelpContextState()
    let calls = 0
    context.setReady(true)
    context.setFetcher(async () => {
      calls += 1
      return { matched: false, anchor_found: false }
    })
    context.setContext({ moduleKey: 'm1' })
    await context.resolve()
    await context.resolve()
    expect(calls).toBe(1)

    await context.retry()
    expect(calls).toBe(2)
  })

  it('竞态：旧上下文的迟到结果被丢弃（令牌 + 上下文键双校验）', async () => {
    const context = new HelpContextState()
    context.setReady(true)
    let releaseFirst: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      releaseFirst = resolve
    })
    context.setFetcher(async (query) => {
      if (query.module_key === 'a') {
        await gate
        return { matched: true, anchor_found: true, article: { id: '1', title: 'A', content: 'a' } }
      }
      return { matched: true, anchor_found: true, article: { id: '2', title: 'B', content: 'b' } }
    })

    context.setContext({ moduleKey: 'a' })
    const first = context.resolve()
    context.setContext({ moduleKey: 'b' })
    await context.resolve()
    releaseFirst()
    await expect(first).resolves.toBeUndefined()

    expect(context.article?.title).toBe('B')
    expect(context.level).toBeUndefined()
  })

  it('上下文变化丢弃旧结果与错误态；重置回全局级', async () => {
    const context = new HelpContextState()
    context.setReady(true)
    context.setFetcher(async () => ({
      matched: true,
      anchor_found: true,
      level: 'module',
      article: { id: '1', title: '模块帮助', content: '<p>x</p>' },
    }))
    context.setContext({ moduleKey: 'm1' })
    await context.resolve()
    expect(context.matched).toBe(true)

    context.setContext({ moduleKey: 'm2' })
    expect(context.result).toBeUndefined()
    expect(context.matched).toBe(false)

    context.reset()
    expect(context.context).toEqual({})
    expect(context.errorMessage).toBe('')
  })

  it('未注入取数器抛 19001（就绪后才报错，未就绪零请求）', async () => {
    const context = new HelpContextState()
    await expect(context.resolve()).resolves.toBeUndefined()
    expect(context.requestCount).toBe(0)

    context.setReady(true)
    await expect(context.resolve()).rejects.toThrow('帮助取数器未注入')
  })
})
