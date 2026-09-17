/** 反馈状态机用例（Kiwi 755）：四态 / 空判定 / 重试。 */

import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/error'
import { useFeedback } from '@/utils/useFeedback'

import { nextTick } from 'vue'

describe('反馈状态机（Kiwi 755）', () => {
  it('loader 成功 → ready；空数组 / null / 空对象 → empty', async () => {
    const ready = useFeedback({ loader: async () => [{ id: 1 }] })
    await ready.load()
    expect(ready.state.value).toBe('ready')
    expect(ready.data.value).toEqual([{ id: 1 }])
    expect(ready.loading.value).toBe(false)

    const emptyList = useFeedback({ loader: async () => [] })
    await emptyList.load()
    expect(emptyList.state.value).toBe('empty')

    const emptyNull = useFeedback<Record<string, unknown> | null>({ loader: async () => null })
    await emptyNull.load()
    expect(emptyNull.state.value).toBe('empty')

    const emptyObject = useFeedback<Record<string, unknown>>({ loader: async () => ({}) })
    await emptyObject.load()
    expect(emptyObject.state.value).toBe('empty')
  })

  it('loader 抛 ApiError → error（code + message 归一，不暴露堆栈）', async () => {
    const wrapper = useFeedback({
      loader: async () => {
        throw new ApiError({ code: 10003, message: 'conflict raw' })
      },
    })
    await wrapper.load()
    expect(wrapper.state.value).toBe('error')
    expect(wrapper.error.value?.code).toBe(10003)
    expect(wrapper.error.value?.message).toBe('操作冲突，请刷新后重试')
    expect(wrapper.error.value?.message).not.toContain('at ')
  })

  it('retry 重新加载成功 → ready', async () => {
    const loader = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(['ok'])
    const feedback = useFeedback({ loader })
    await feedback.load()
    expect(feedback.state.value).toBe('error')
    expect(feedback.error.value?.message).toBe('network down')

    await feedback.retry()
    expect(feedback.state.value).toBe('ready')
    expect(feedback.data.value).toEqual(['ok'])
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('自定义 isEmpty / errorText 与 onError', async () => {
    const onError = vi.fn()
    const feedback = useFeedback<{ total: number }>({
      loader: async () => ({ total: 0 }),
      isEmpty: (data) => data.total === 0,
      onError,
    })
    await feedback.load()
    expect(feedback.state.value).toBe('empty')

    const failing = useFeedback({
      loader: async () => {
        throw new Error('boom')
      },
      errorText: () => '友好提示',
      onError,
    })
    await failing.load()
    expect(failing.error.value?.message).toBe('友好提示')
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('immediate 挂载即加载与 loading 计算', async () => {
    let resolveLoader: ((value: number) => void) | null = null
    const feedback = useFeedback({
      loader: () =>
        new Promise<number>((resolve) => {
          resolveLoader = resolve
        }),
      immediate: true,
    })
    expect(feedback.state.value).toBe('loading')
    expect(feedback.loading.value).toBe(true)

    resolveLoader?.(1)
    await nextTick()
    await Promise.resolve()
    expect(feedback.state.value).toBe('ready')
    expect(feedback.loading.value).toBe(false)
  })
})
